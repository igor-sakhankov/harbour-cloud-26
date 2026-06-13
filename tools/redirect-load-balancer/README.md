# redirect-load-balancer

A small redirect load balancer that spreads traffic across several instances of
the StarHarbour payments app. Plain Python 3, standard library only, nothing to
install.

It doesn't proxy. For each request it picks a healthy backend and replies with an
HTTP **302** whose `Location` points at that backend; the client follows the
redirect and talks to the backend directly. That keeps the balancer stateless and
cheap — it never reads request or response bodies.

## The four design questions

**HTTP 302.** Every request gets a `302 Found` with `Location: <backend><same
path and query>`. The client follows it on its own. The balancer holds no
connection to the backend and copies no body.

> Caveat: a 302 can make some clients turn a `POST` into a `GET` when they follow
> it. If you need the method preserved, set `redirect_status` to `307` in
> `config.json` — the code treats the status as configurable; 302 is the default
> because that's what this assignment asks for.

**How to get the list of services.** Backends are read from `config.json` at
startup, and the `LB_BACKENDS` env var (comma-separated) or `--backends` flag can
override the list. The list lives behind a small pool object, so swapping the
static list for a real registry (Consul, Eureka, Kubernetes Endpoints, DNS) later
is a local change.

**How to do health checks.** A background thread probes each backend on an
interval (`GET` the health path, default `/api/v1/payments?storeId=__lb_health__`,
which the app answers with `200 []`). To avoid flapping it uses thresholds: a
backend drops out after `fail_threshold` consecutive failures (default 2) and
comes back after `rise_threshold` consecutive successes (default 2). Only healthy
backends get traffic; if none are healthy the balancer returns `503`.

**What algorithm.** Round-robin over the healthy backends. It's simple and fair,
and it fits a redirect balancer: each request is independent and the balancer
never sees the connection afterwards, so connection-aware schemes like
least-connections don't apply. Random would also work but spreads less evenly;
weighting is unnecessary for identical instances.

## Run it

```bash
cd tools/redirect-load-balancer

# 1. start a few payments instances on 8081..8083 (builds the jar first)
./run_instances.sh 3 8081

# 2. start the balancer on :8080 in front of them
python3 -m loadbalancer --config config.json

# 3. send some traffic and see where it lands
python3 demo.py http://localhost:8080 12
```

Kill one instance (`kill <pid>` from `/tmp/lb-instances/pids`), wait a second for
the health check to notice, and run `demo.py` again — the traffic moves to the
remaining instances.

## Options

| Flag | Meaning |
|---|---|
| `--config` | Path to `config.json` (default `config.json`). |
| `--host` / `--port` | Listen address (override the config). |
| `--backends` | Comma-separated backend URLs (overrides config and `LB_BACKENDS`). |

Config keys: `backends`, `listen_host`, `listen_port`, `health_path`,
`health_interval`, `health_timeout`, `fail_threshold`, `rise_threshold`,
`redirect_status`.

## Tests

```bash
cd tools/redirect-load-balancer
python3 -m unittest discover -s tests
```

Covers round-robin and the health-state thresholds, the 302/503 responses, and an
end-to-end test that runs two in-process backends behind the balancer and checks
both that traffic spreads and that it fails over when one backend is stopped.
