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
| **Async bulk processing** — bulk requests are accepted immediately (202), persisted to Postgres, and processed off the request thread; clients poll for completion | `BulkPaymentController`, `BulkPaymentService`, `BulkPaymentProcessor` |
| **Sharded Postgres** — the payments table is spread across N independent Postgres instances; shard count is configured statically in `application.properties` | `ShardRouter`, `ShardedPaymentRepository` |
| **Network fault injection** — Toxiproxy sits in front of the app so you can simulate latency, packet loss, and timeouts without changing a line of code | `compose.yaml`, `toxiproxy.json` |
| **Transaction viewer UI** — a vanilla-JS single-page app served as a static resource | `src/main/resources/static/index.html` |

### API surface

All endpoints are under `/api/v1/payments`.

#### Register a single payment (synchronous)
```
POST /api/v1/payments
Store-Id: <store-id>
Idempotency-Key: <uuid>       # optional
Content-Type: application/json

{
  "coffeeType": "LATTE",
  "price": 3.50,
  "currency": "EUR",
  "loyaltyCardId": "card-123"
}
```
Returns `201 Created` for a new payment, `200 OK` on idempotent replay.

#### Submit a bulk payment job (asynchronous)
```
POST /api/v1/payments/bulk
Content-Type: application/json

[
  {
    "storeId": "store-london-01",
    "idempotencyKey": "order-abc-1",   // optional — auto-generated if absent
    "coffeeType": "LATTE",
    "price": 3.50,
    "currency": "EUR",
    "loyaltyCardId": "card-123"
  },
  ...
]
```
Returns `202 Accepted`:
```json
{ "jobId": "uuid" }
```
The job is stored in Postgres immediately. Items are processed asynchronously by `BulkPaymentProcessor` — each payment is registered in the existing `PaymentService` (the "remote system") and persisted to the sharded `payments` table. When all items are done the job status flips to `DONE`.

#### Poll bulk job status
```
GET /api/v1/payments/bulk/{jobId}
```
Returns:
```json
{
  "id": "uuid",
  "status": "PENDING",     // or "DONE"
  "totalCount": 5,
  "createdAt": "2024-01-01T12:00:00Z"
}
```

#### List payments for a store
```
GET /api/v1/payments?storeId=<store-id>
```

#### Get a single payment
```
GET /api/v1/payments/{paymentId}
```

#### Batch import payments from CSV
```
POST /api/v1/payments/import
Content-Type: multipart/form-data

file: <CSV file>
```
See [CSV Import Guide](./docs/CSV_IMPORT.md) for full documentation.

### Coffee types
`ESPRESSO` · `DOUBLE_ESPRESSO` · `AMERICANO` · `LATTE` · `CAPPUCCINO` · `FLAT_WHITE` · `MOCHA` · `CORTADO` · `MACCHIATO` · `COLD_BREW`

---

## How sharding works

Shard routing is a single line:

```java
shards.get(Math.abs(storeId.hashCode()) % shards.size())
```

Each Postgres instance is a peer — no coordinator, no cross-shard joins. The `bulk_jobs` table lives on shard 0 as the metadata node. Schema is created on startup via `CREATE TABLE IF NOT EXISTS`; no migration framework needed at this scale.

To add shards, extend `application.properties`:

```properties
app.db.shard-count=3
app.db.shards[2].url=jdbc:postgresql://localhost:5434/payments
app.db.shards[2].username=postgres
app.db.shards[2].password=postgres
```

and add a matching service in `compose.yaml`. Resharding is out of scope — this is hash-mod routing, intentionally simple.

---

## Requirements

| Tool | Version |
|---|---|
| Java | 25 (set via `.sdkmanrc` — run `sdk use` if you use [SDKMAN](https://sdkman.io/)) |
| Docker & Docker Compose | any recent version |
| Gradle | bundled via `./gradlew` — no separate install needed |

---

## Running the application

Spring Boot's Docker Compose integration starts Toxiproxy and both Postgres shards automatically when you launch the app. Postgres healthchecks are in place but `readiness.wait=never` is set to avoid the Toxiproxy proxy-to-self deadlock — `ShardRouter` retries schema creation for up to 15 seconds to cover the gap.

```bash
./gradlew bootRun
```

| Port | What's there |
|---|---|
| **8080** | Spring Boot directly |
| **9091** | Toxiproxy proxy — use for fault injection |
| **8474** | Toxiproxy management API |
| **5432** | Postgres shard 0 |
| **5433** | Postgres shard 1 |

Open the transaction viewer at **http://localhost:8080**.

### Run tests

```bash
./gradlew test
```

Tests use MockMvc and the in-memory store — no Docker needed.

---

## Trying async bulk payments

```bash
# Submit a bulk job
curl -s -X POST http://localhost:8080/api/v1/payments/bulk \
  -H "Content-Type: application/json" \
  -d '[
    {"storeId":"store-1","idempotencyKey":"k1","coffeeType":"LATTE","price":3.50,"currency":"EUR","loyaltyCardId":"card-1"},
    {"storeId":"store-2","idempotencyKey":"k2","coffeeType":"ESPRESSO","price":2.00,"currency":"EUR","loyaltyCardId":"card-2"}
  ]'
# → {"jobId":"<uuid>"}

# Poll until DONE
curl -s http://localhost:8080/api/v1/payments/bulk/<uuid>
# → {"id":"<uuid>","status":"DONE","totalCount":2,"createdAt":"..."}
```

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
│   │   │   ├── CloudApplication.java          # Spring Boot entry point (@EnableAsync, @ConfigurationPropertiesScan)
│   │   │   └── payments/
│   │   │       ├── Payment.java               # Domain record
│   │   │       ├── PaymentRequest.java        # Validated request body
│   │   │       ├── PaymentResponse.java       # API response shape
│   │   │       ├── CoffeeType.java            # Enum of coffee varieties
│   │   │       ├── PaymentController.java     # Single-payment REST endpoints
│   │   │       ├── PaymentService.java        # Idempotency logic
│   │   │       ├── PaymentRepository.java     # In-memory store (single-payment path)
│   │   │       ├── PaymentConfig.java         # Clock bean
│   │   │       ├── PaymentExceptionHandler.java # 400 error shaping
│   │   │       ├── DbConfig.java              # @ConfigurationProperties for shard URLs
│   │   │       ├── ShardRouter.java           # Datasource creation, hash routing, schema init
│   │   │       ├── BulkJob.java               # Bulk job domain record
│   │   │       ├── BulkJobRepository.java     # CRUD on bulk_jobs (shard 0)
│   │   │       ├── ShardedPaymentRepository.java # Writes payments to correct shard
│   │   │       ├── BulkPaymentItem.java       # Single item in a bulk request
│   │   │       ├── BulkPaymentProcessor.java  # @Async worker — registers payments, marks job done
│   │   │       ├── BulkPaymentService.java    # Submits jobs, exposes status queries
│   │   │       ├── BulkPaymentController.java # POST /bulk, GET /bulk/{id}
│   │   │       ├── CsvPaymentRecord.java      # CSV row DTO
│   │   │       ├── CsvImportResult.java       # CSV import result DTO
│   │   │       ├── CsvPaymentImportService.java # CSV processor
│   │   │       ├── CsvImportController.java   # CSV import endpoint
│   │   │       └── RestTemplateConfig.java    # REST client config
│   │   └── resources/
│   │       ├── application.properties         # App + shard config
│   │       └── static/index.html             # Transaction viewer UI
│   └── test/
│       └── java/space/harbour/cloud/payments/
│           └── PaymentControllerTest.java
├── docs/
│   └── CSV_IMPORT.md
├── compose.yaml          # Toxiproxy + postgres-0 + postgres-1
├── toxiproxy.json
├── build.gradle.kts
└── settings.gradle.kts
```

---

## Course context

This repository is the practical companion to the **Distributed Systems & Cloud** lecture series. Each change targets a single distributed-systems concept so students can study it in isolation:

- **Idempotency** — `PaymentService` + `PaymentRepository` (ConcurrentHashMap, putIfAbsent)
- **Async processing** — bulk endpoint returns immediately; `BulkPaymentProcessor` runs on a Spring task-executor thread
- **Horizontal sharding** — `ShardRouter` routes by `storeId.hashCode() % shardCount`; schema bootstraps itself on startup
- **Network faults** — Toxiproxy injects latency/timeouts transparently
