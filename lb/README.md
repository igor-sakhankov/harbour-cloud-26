# Redirect Load Balancer

A small, dependency-free **HTTP 302 redirect load balancer** for the StarHarbour
Payments service (the app from homework 1). Instead of proxying traffic, it
answers each request with a [`302 Found`](https://en.wikipedia.org/wiki/HTTP_302)
pointing the client at one of the healthy app instances; the client then talks to
that instance directly.

```
        ┌──────────────┐   302 Location: http://app-2:8082/api/v1/payments
client ─┤ load balancer├──────────────────────────────────────────────►
        └──────┬───────┘                                          │
               │ health checks (background)                       │ follow redirect
        ┌──────┴───────┬───────────────┐                          ▼
        ▼              ▼               ▼                    ┌───────────┐
   app-1:8081     app-2:8082     app-3:8083  ◄───────────── │  app-2    │
                                                            └───────────┘
```

## Why a redirect LB (and the trade-off)

A redirect LB is **stateless** — it never carries request or response bodies, so
it uses almost no CPU/memory and can't become a bandwidth bottleneck. The cost:

- One extra round trip (client → LB → client → backend).
- Backend addresses are exposed to clients, so they must be routable from the
  client. Good for internal/service-to-service traffic; usually not what you want
  for a public edge LB (where you'd terminate and proxy instead).
- A plain `302` invites clients to downgrade `POST` to `GET`. The course's POS
  clients re-issue the original method against `Location`, which is what we rely
  on. (Use `307 Temporary Redirect` instead if you need to *guarantee* method and
  body are preserved — change the one status code in `make_handler`.)

## The four design questions

### 1. How to get the list of available services

Backends come from **static configuration** — `config.json` (or the `LB_BACKENDS`
env var, comma-separated, which overrides the file). This is the right amount of
machinery for a fixed, hand-managed fleet.

```json
{ "backends": ["http://localhost:8081", "http://localhost:8082"] }
```

`BackendPool` is the **single discovery seam**. Its `replace(urls)` method swaps
the backend set at runtime while preserving the health state of URLs that stay.
To move to dynamic discovery (Consul/Eureka service registry, DNS SRV records, or
Kubernetes `Endpoints`), you add one poller that calls `pool.replace(...)` — the
strategy, health checker, and HTTP layer don't change.

### 2. How to do health checks

A background thread (`HealthChecker`) probes every backend on a fixed interval
(`health_interval_seconds`, default 5s) and flips a per-backend `healthy` flag.
**Only healthy backends are ever handed out.**

- The probe is an HTTP `GET` to `<backend><health_path>` with a timeout
  (`health_timeout_seconds`, default 2s). Default path is `/` because the homework-1
  app serves its static viewer there with a `200` and has no actuator endpoint.
  Point `health_path` at `/actuator/health` (or any cheap endpoint) if one exists.
- **Health semantics**: any `2xx`/`3xx` → healthy; a `4xx` still proves the process
  is up and serving, so it counts as healthy; `5xx`, connection refused, or timeout
  → unhealthy. This is *passive liveness* — it detects a down/crashed instance, not
  a slow or semantically-broken one.
- One synchronous probe runs at startup so the LB never serves traffic with stale
  health. Recovery is automatic: a backend that starts answering again is picked up
  on the next interval.
- The probe function is injected, so tests drive health transitions deterministically
  without real sockets.

### 3. What algorithm to use

**Round-robin over the currently-healthy set** (default), with **random** also
available (`"algorithm": "round_robin" | "random"` in config).

- *Round-robin* gives an even spread with a single global counter. Because it
  cycles over the *healthy* candidates each time, removing or restoring a backend
  doesn't skew the distribution.
- *Random* is stateless and approaches an even spread at volume — handy when you
  run multiple LB processes that can't share a counter.

Both are O(1) per request and assume backends are roughly equal. The `BalancingStrategy`
interface is the extension point: weighted round-robin or least-connections would
each be a new `choose()` implementation. (Least-connections needs the LB to observe
request completion, which a *redirect* LB can't — it never sees the response — so
round-robin/random are the natural fits here.)

### 4. Putting it together — the request path

1. Request arrives at the LB (any method).
2. `LoadBalancer.next_backend()` asks the strategy to pick from `pool.healthy()`.
3. No healthy backend → **`503 Service Unavailable`**.
4. Otherwise → **`302`** with `Location: <backend><original-path-and-query>` and
   `Cache-Control: no-store` (the target changes every request, so it must not be
   cached).

The LB also exposes `GET /__lb/health` → `200 OK` so you can health-check the
balancer itself.

## Running it

Start a few instances of the homework-1 app on different ports, e.g.:

```bash
SERVER_PORT=8081 ./gradlew bootRun   # in three terminals, ports 8081/8082/8083
```

Edit `lb/config.json` to list those backends, then:

```bash
python3 lb/load_balancer.py --config lb/config.json
# or override backends inline:
LB_BACKENDS="http://localhost:8081,http://localhost:8082" python3 lb/load_balancer.py
```

Watch it redirect (the POS terminals / curl follow the `Location` automatically):

```bash
# See the raw 302 and where it points:
curl -i http://localhost:8080/api/v1/payments?storeId=store-london-01

# Follow the redirect through to a backend:
curl -L http://localhost:8080/api/v1/payments?storeId=store-london-01
```

## Tests

Standard-library `unittest`, no install step. They cover the selection logic,
health-driven exclusion/recovery, and a full end-to-end `302` over real sockets
(spinning up stub backends + the real LB, asserting the redirect, following it,
and verifying the `503` when every backend is down).

```bash
python3 -m unittest discover -s lb -v
# or
python3 lb/test_load_balancer.py
```

## Files

| File | Purpose |
|---|---|
| `load_balancer.py` | LB core: config, backend pool, strategies, health checker, HTTP front end |
| `config.json` | Backend list + tuning (algorithm, health path/interval/timeout) |
| `test_load_balancer.py` | Unit + end-to-end tests |
