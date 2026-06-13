# load-balancer

A redirect load balancer that distributes traffic across multiple instances of
the harbour-cloud payments app. Instead of proxying, it answers each request
with an HTTP redirect pointing the client at a healthy backend, so it stays
stateless and never touches the request body.

## Run

```bash
pnpm install
LB_BACKENDS=http://localhost:8081,http://localhost:8082,http://localhost:8083 pnpm start
```

Then point the HW1 client at the balancer:

```bash
(cd ../csv-uploader && pnpm start sample.csv --url http://localhost:8080)
```

Or boot everything (3 app instances + the LB) with one script:

```bash
./run-demo.sh        # needs ../harbour-cloud-26 built (./gradlew bootJar)
```

`GET /__lb/status` shows live backend health.

## Config (env)

| Var | Default | Meaning |
|---|---|---|
| `LB_BACKENDS` | — (required) | comma-separated backend URLs |
| `PORT` | `8080` | port the LB listens on |
| `HEALTH_INTERVAL_MS` | `10000` | health-probe interval |

## Design

**HTTP redirect (307, not 302).** The LB replies `307` + a `Location` header for
a chosen backend; the client then talks to that backend directly. A `302` would
be the literal spec, but browsers/`fetch` downgrade a followed `302` on a `POST`
to a bodyless `GET` — which would drop the payment. `307` preserves the method
and body, so the client's POST (and its headers) survive the redirect untouched.

**Service discovery.** Backends are read from the `LB_BACKENDS` env var at
startup (`config.ts`). This is the seam a real registry (Consul / k8s Endpoints)
would replace.

**Health check.** A background loop (`healthChecker.ts`) probes every backend
every 10s with `GET /api/v1/payments?storeId=lb-health-check` (the app has no
dedicated health endpoint). `< 500` = healthy; `5xx` / timeout / connection
refused = unhealthy. Only healthy backends receive traffic; recovery is
automatic. Active probing is required because, after the redirect, real traffic
goes client→backend directly and the LB never sees its outcome.

**Algorithm — consistent hash on `Idempotency-Key`.** Each request is routed by
hashing its `Idempotency-Key` header onto a hash ring (`balancer.ts`). This keeps
**retries of the same payment on the same backend**, so the server's in-memory
idempotency dedup still works (exactly-once) — plain round-robin would scatter
retries across instances and re-create duplicates. Because the client's keys are
random UUIDs, they spread ~evenly across backends, so we keep good load
distribution too. A request with no key, or a failover when the hashed backend
is down, picks a **random healthy** backend.

**No healthy backends** → `503 Service Unavailable` (with `Retry-After`).

## Files

| File | Concern |
|---|---|
| `src/config.ts` | service discovery (env) |
| `src/backendPool.ts` | backend set + health state |
| `src/healthChecker.ts` | active health probing |
| `src/balancer.ts` | hash-ring routing + failover |
| `src/server.ts` | HTTP front end, 307 redirect, status endpoint |
