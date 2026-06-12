# StarHarbour Payments Service

A Spring Boot REST service that records coffee-shop payments for the fictional **StarHarbour** chain.
Built as the running example for the [Harbour.Space](https://harbour.space/) **Cloud Computing for Software Engineers** course — each iteration of the codebase introduces a new distributed-systems concept on top of this foundation.

---

## What it does

The service exposes a small Payments API used by point-of-sale terminals in StarHarbour stores:

| Concept | Where it lives |
|---|---|
| **Idempotent writes** — a terminal can safely retry after a network timeout without creating a duplicate payment | `PaymentService` + `PaymentRepository` (keyed on `Store-Id` × `Idempotency-Key`) |
| **Input validation** — structured `400 Bad Request` responses via Jakarta Bean Validation | `PaymentRequest`, `PaymentExceptionHandler` |
| **Network fault injection** — Toxiproxy sits in front of the app so you can simulate latency, packet loss, and timeouts without changing a line of code | `compose.yaml`, `toxiproxy.json` |
| **Transaction viewer UI** — a vanilla-JS single-page app served as a static resource | `src/main/resources/static/index.html` |

### API surface

All endpoints are under `/api/v1/payments`.

#### Register a payment
```
POST /api/v1/payments
Store-Id: <store-id>          # required — identifies the store
Idempotency-Key: <uuid>       # optional — supply to make retries safe
Content-Type: application/json

{
  "coffeeType": "LATTE",      // see CoffeeType enum for all values
  "price": 3.50,
  "currency": "EUR",          // ISO-4217, e.g. EUR / USD / GBP
  "loyaltyCardId": "card-123"
}
```
Returns `201 Created` for a new payment, `200 OK` when the same `Idempotency-Key` has already been processed (the original payment is echoed back unchanged).

#### List payments for a store
```
GET /api/v1/payments?storeId=<store-id>
```

#### Get a single payment
```
GET /api/v1/payments/{paymentId}
```

### Coffee types
`ESPRESSO` · `DOUBLE_ESPRESSO` · `AMERICANO` · `LATTE` · `CAPPUCCINO` · `FLAT_WHITE` · `MOCHA` · `CORTADO` · `MACCHIATO` · `COLD_BREW`

---

## Requirements

| Tool | Version |
|---|---|
| Java | 25 (set via `.sdkmanrc` — run `sdk use` if you use [SDKMAN](https://sdkman.io/)) |
| Docker & Docker Compose | any recent version |
| Gradle | bundled via `./gradlew` — no separate install needed |

---

## Running the application

### 1. Start the Spring Boot app (with Toxiproxy sidecar)

Spring Boot's Docker Compose integration starts Toxiproxy automatically when you launch the app.

```bash
./gradlew bootRun
```

The app is now reachable on two ports:

| Port | What's there |
|---|---|
| **8080** | Spring Boot directly |
| **9091** | Toxiproxy proxy — use this to experience injected faults |
| **8474** | Toxiproxy management API |

Open the transaction viewer UI at **http://localhost:8080** (or **http://localhost:9091** to route through the proxy).

### 2. Run tests

```bash
./gradlew test
```

Tests use MockMvc — no Docker needed.

---

## Trying idempotency

```bash
# First call — creates the payment (201)
curl -s -w "\nHTTP %{http_code}\n" -X POST http://localhost:8080/api/v1/payments \
  -H "Store-Id: store-london-01" \
  -H "Idempotency-Key: order-abc-123" \
  -H "Content-Type: application/json" \
  -d '{"coffeeType":"LATTE","price":3.50,"currency":"EUR","loyaltyCardId":"card-999"}'

# Exact same call — replays the original payment (200, same paymentId)
curl -s -w "\nHTTP %{http_code}\n" -X POST http://localhost:8080/api/v1/payments \
  -H "Store-Id: store-london-01" \
  -H "Idempotency-Key: order-abc-123" \
  -H "Content-Type: application/json" \
  -d '{"coffeeType":"LATTE","price":3.50,"currency":"EUR","loyaltyCardId":"card-999"}'
```

## Injecting network faults via Toxiproxy

Point your client at **port 9091** and use the Toxiproxy management API on **port 8474**.

```bash
# Add 2 s latency with 500 ms jitter
curl -X POST http://localhost:8474/proxies/spring-boot-app/toxics \
  -H "Content-Type: application/json" \
  -d '{"name":"latency","type":"latency","attributes":{"latency":2000,"jitter":500}}'

# Simulate a total connection timeout
curl -X POST http://localhost:8474/proxies/spring-boot-app/toxics \
  -H "Content-Type: application/json" \
  -d '{"name":"timeout","type":"timeout","attributes":{"timeout":0}}'

# Remove the toxic and restore normal behaviour
curl -X DELETE http://localhost:8474/proxies/spring-boot-app/toxics/latency
```

---

## Project layout

```
harbour-cloud-26/
├── src/
│   ├── main/
│   │   ├── java/space/harbour/cloud/
│   │   │   ├── CloudApplication.java          # Payments entry point (scans payments only)
│   │   │   ├── lb/                             # Redirect (302) load balancer — a 2nd Spring Boot app
│   │   │   │   ├── LoadBalancerApplication.java # Entry point (scanBasePackages = ...lb)
│   │   │   │   ├── LbProperties.java            # lb.* config
│   │   │   │   ├── InstanceRegistry.java        # health state + round-robin
│   │   │   │   ├── ActiveHealthChecker.java     # @Scheduled /actuator/health probe
│   │   │   │   └── RedirectController.java      # /api/** → 302; /lb/report; /lb/status
│   │   │   └── payments/
│   │   │       ├── Payment.java               # Domain record
│   │   │       ├── PaymentRequest.java        # Validated request body
│   │   │       ├── PaymentResponse.java       # API response shape
│   │   │       ├── CoffeeType.java            # Enum of coffee varieties
│   │   │       ├── PaymentController.java     # REST endpoints
│   │   │       ├── PaymentService.java        # Idempotency logic
│   │   │       ├── PaymentRepository.java     # In-memory store
│   │   │       ├── PaymentConfig.java         # Clock bean
│   │   │       └── PaymentExceptionHandler.java # 400 error shaping
│   │   └── resources/
│   │       ├── application.properties
│   │       ├── application-lb.properties     # Load balancer profile (port 8090, instances, thresholds)
│   │       └── static/index.html             # Transaction viewer UI
│   └── test/
│       └── java/space/harbour/cloud/payments/
│           └── PaymentControllerTest.java
├── compose.yaml          # Toxiproxy sidecar
├── toxiproxy.json        # Proxy config: 9091 → localhost:8080
├── build.gradle.kts
└── settings.gradle.kts
```

---

## Course context

This repository is the practical companion to the **Distributed Systems & Cloud** lecture series. The storage layer is intentionally in-memory (a `ConcurrentHashMap`) — later modules swap it for a real database, add messaging via Kafka, and deploy to AWS. Each change targets a single distributed-systems concept so students can study it in isolation.


## CSV payment importer

End-of-day automation for store owners: read a notebook of payments from a CSV
file and **reliably** propagate every row to the Payments API ("the Central
System"), surviving network faults without ever creating a duplicate payment.

Lives in `space.harbour.cloud.importer.PaymentCsvImporter`. It is a plain HTTP
client (`java.net.http.HttpClient`) — no Spring context required — so it can run
standalone against a local app or any deployed instance.

### CSV format

Header is order-independent. `idempotencyKey` and `loyaltyCardId` may be blank
(but note the API rejects a blank `loyaltyCardId` with 400 in the current build).

```csv
storeId,idempotencyKey,coffeeType,price,currency,loyaltyCardId
store-london-01,2026-06-10-0001,LATTE,3.50,EUR,card-999
store-london-01,2026-06-10-0002,ESPRESSO,2.00,EUR,card-111
```

| Column           | Required | Notes                                                        |
|------------------|----------|--------------------------------------------------------------|
| `storeId`        | yes      | Sent as the `Store-Id` header.                               |
| `idempotencyKey` | no       | Natural "notebook entry id". If blank, a stable key is derived from the row content + position, so re-running the same file stays idempotent. |
| `coffeeType`     | yes      | One of the `CoffeeType` enum values.                         |
| `price`          | yes      | Numeric; emitted to JSON verbatim.                           |
| `currency`       | yes      | ISO-4217.                                                    |
| `loyaltyCardId`  | no       | Omitted from the request body when blank.                    |

### Running

```bash
# against the app directly
./gradlew importCsv --args="samples/payments-sample.csv http://localhost:8080"

# through Toxiproxy, to exercise fault tolerance
./gradlew importCsv --args="samples/payments-sample.csv http://localhost:9091"
```

Output reports per-row outcome and a final tally:

```
done: created=5 alreadyExisted=0 skipped=0 failed=0
```

Exit code is `0` only when nothing was left undelivered.

### How "reliably" is achieved

Three independent layers:

1. **Idempotency** — every row carries a stable `Idempotency-Key`. The server
   dedupes on `(Store-Id x Idempotency-Key)` and replays the original payment
   with `200` on a repeat, so a retried POST never creates a duplicate.
2. **Retries with capped exponential backoff + full jitter** — transient
   failures (connection drops, timeouts, `408`/`429`/`5xx`) are retried;
   `Retry-After` is honoured on `429`. Permanent failures (`400`/`422`
   validation, `401`/`403`/`404`) are **not** retried — retrying bad data is
   pointless, so the row is logged and skipped.
3. **A resumable journal** — confirmed keys are appended to `import-journal.txt`;
   a re-run skips already-confirmed rows. The journal is an optimisation and
   audit trail — the real exactly-once guarantee comes from server-side
   idempotency, not the journal.

### Verifying it (with Toxiproxy)

- **Idempotent replay** — run the importer twice; the second run reports
  `alreadyExisted` / `skipped` and `GET /api/v1/payments?storeId=...` still
  returns the original count, never doubled.
- **Retry under faults** — inject latency or a timeout toxic on port `9091`,
  then import through the proxy. The log shows repeated `attempt N` entries; the
  payment count never grows beyond the number of CSV rows.
- **No duplicates even when everything fails** — under a permanent timeout
  toxic, every row exhausts its retries and the importer exits non-zero, yet the
  store still holds exactly one payment per already-created row — proof that
  retries are duplicate-safe.

Automated equivalents of these scenarios run without Docker in
`PaymentCsvImporterTest` (a self-contained fake server that fails twice then
succeeds), covering retry-then-create, journal-based skip, and server-side
idempotent replay.

The importer also **follows 302 redirects manually** — Java's `HttpClient` will
not auto-redirect a POST, so on a `302 Found` it reads the `Location` header and
re-issues the *same* POST (same body, same `Store-Id` / `Idempotency-Key`) to the
target, bounded by a small max-redirect count. This lets it talk to the redirect
load balancer below; idempotency keeps the redirect-retries duplicate-safe.


## Redirect (HTTP 302) load balancer

A **second, standalone Spring Boot app** in this same module
(`space.harbour.cloud.lb`) that spreads `/api/**` traffic across several payment
instances. It does **not** proxy: on each `/api/**` request it picks one healthy
instance and answers `302 Found` with a `Location` header, and the client follows
the redirect to that instance directly.

| Piece | Responsibility |
|---|---|
| `LoadBalancerApplication` | Entry point — `scanBasePackages = "space.harbour.cloud.lb"` (so it never boots the payments controllers), `@EnableScheduling`, `@EnableConfigurationProperties` |
| `LbProperties` (`lb.*`) | Static instance list, health path, probe interval/timeout, and the two state-machine thresholds |
| `InstanceRegistry` | Instance list + health state + round-robin `next()` (atomic counter over the *currently healthy* set) + `recordResult(...)` |
| `ActiveHealthChecker` | `@Scheduled` probe of each instance's `/actuator/health` via `java.net.http.HttpClient` |
| `RedirectController` | `/api/**` → `302`; `POST /lb/report`; `GET /lb/status` |

**Health model — both active and passive, one state machine.** Active probes
(scheduled) and passive client reports (`POST /lb/report?instance=...&ok=false`)
feed the *same* threshold-based machine: an instance is **ejected after
`unhealthy-after` consecutive failures** and **re-admitted only after
`healthy-after` consecutive successes**, so it never flaps. Only `/api/**` is
intercepted, so `favicon.ico`, `/error`, and `/lb/*` are never redirected. The
302 `Location` preserves the original path **and** query string. When no instance
is healthy, `/api/**` returns **503**.

Configuration lives in `application-lb.properties` (activated by the `lb` profile):
`server.port=8090`, `lb.instances=http://localhost:8081,http://localhost:8082`,
`lb.health-path=/actuator/health`, `lb.interval=2s`, `lb.timeout=1s`,
`lb.unhealthy-after=2`, `lb.healthy-after=2`.

### Running it

Start **two backend instances** on 8081 / 8082 (the actuator starter exposes
`/actuator/health`), and the **balancer** on 8090. The easiest way to run more
than one backend is from the fat jar:

```bash
# build once
./gradlew bootJar

# two backend instances (disable docker-compose so they don't fight over Toxiproxy)
java -jar build/libs/cloud-0.0.1-SNAPSHOT.jar --server.port=8081 --spring.docker.compose.enabled=false
java -jar build/libs/cloud-0.0.1-SNAPSHOT.jar --server.port=8082 --spring.docker.compose.enabled=false

# the load balancer (separate task; normal `bootRun` only starts the payments app)
./gradlew bootRunLb
```

### Verifying it

```bash
# both instances HEALTHY
curl -s http://localhost:8090/lb/status

# two /api calls -> 302 with Location alternating between :8081 and :8082
curl -si "http://localhost:8090/api/v1/payments?storeId=store-1" | grep -i '^\(HTTP\|location:\)'
curl -si "http://localhost:8090/api/v1/payments?storeId=store-1" | grep -i '^location:'

# kill one instance; within ~2 intervals (~4 s) it is ejected and all traffic
# goes to the survivor
curl -s http://localhost:8090/lb/status

# with both down, /api returns 503
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8090/api/v1/payments
```