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

## Redirect load balancer

The app also includes a small redirect-based load balancer. Requests sent to
`/lb/<target-path>` receive `302 Found`; the `Location` header points to a
healthy backend instance and preserves the original target path and query
string.

This uses `302` because the homework asks for it. For production write requests,
`307` or `308` is usually safer because those status codes require clients to
preserve the original HTTP method and body when following the redirect.

### How to get the list of available services

Backend app instances are configured explicitly:

```properties
load-balancer.instances=http://localhost:8081,http://localhost:8082
```

The same value can be supplied as an environment variable:

```bash
LOAD_BALANCER_INSTANCES=http://localhost:8081,http://localhost:8082 ./gradlew bootRun
```

The load balancer exposes its configured backends and latest health results at:

```bash
curl http://localhost:8080/lb/backends
```

### How health checks work

Every backend is checked periodically with an HTTP `GET` to its health endpoint.
The default is:

```properties
load-balancer.health-path=/actuator/health
load-balancer.health-timeout=1s
load-balancer.health-check-interval-ms=5000
```

Any `2xx` response marks the backend healthy. Timeouts, connection failures, and
non-`2xx` responses mark it unhealthy. If no healthy backend exists, the load
balancer returns `503 Service Unavailable` instead of redirecting.

### Algorithm

The selection algorithm is round-robin across healthy backends only. Round-robin
is deterministic, simple to inspect during homework, and spreads requests evenly
when all app instances have the same capacity.

### Running a local demo

Start two app instances on different ports:

```bash
SERVER_PORT=8081 SPRING_DOCKER_COMPOSE_ENABLED=false ./gradlew bootRun
SERVER_PORT=8082 SPRING_DOCKER_COMPOSE_ENABLED=false ./gradlew bootRun
```

Then start a load-balancer instance:

```bash
SERVER_PORT=8080 \
LOAD_BALANCER_INSTANCES=http://localhost:8081,http://localhost:8082 \
SPRING_DOCKER_COMPOSE_ENABLED=false \
./gradlew bootRun
```

Example redirect:

```bash
curl -i "http://localhost:8080/lb/api/v1/payments?storeId=store-london-01"
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
│   │   │   ├── CloudApplication.java          # Spring Boot entry point
│   │   │   ├── payments/
│   │   │   │   ├── Payment.java               # Domain record
│   │   │   │   ├── PaymentRequest.java        # Validated request body
│   │   │   │   ├── PaymentResponse.java       # API response shape
│   │   │   │   ├── CoffeeType.java            # Enum of coffee varieties
│   │   │   │   ├── PaymentController.java     # REST endpoints
│   │   │   │   ├── PaymentService.java        # Idempotency logic
│   │   │   │   ├── PaymentRepository.java     # In-memory store
│   │   │   │   ├── PaymentConfig.java         # Clock bean
│   │   │   │   └── PaymentExceptionHandler.java # 400 error shaping
│   │   │   └── loadbalancer/
│   │   │       ├── RedirectLoadBalancerController.java # 302 redirect endpoint
│   │   │       └── RoundRobinRedirectLoadBalancer.java # healthy round-robin selector
│   │   └── resources/
│   │       ├── application.properties
│   │       └── static/index.html             # Transaction viewer UI
│   └── test/
│       └── java/space/harbour/cloud/
│           ├── payments/PaymentControllerTest.java
│           └── loadbalancer/
│               ├── RedirectLoadBalancerControllerTest.java
│               └── RoundRobinRedirectLoadBalancerTest.java
├── compose.yaml          # Toxiproxy sidecar
├── toxiproxy.json        # Proxy config: 9091 → localhost:8080
├── build.gradle.kts
└── settings.gradle.kts
```

---

## Course context

This repository is the practical companion to the **Distributed Systems & Cloud** lecture series. The storage layer is intentionally in-memory (a `ConcurrentHashMap`) — later modules swap it for a real database, add messaging via Kafka, and deploy to AWS. Each change targets a single distributed-systems concept so students can study it in isolation.
