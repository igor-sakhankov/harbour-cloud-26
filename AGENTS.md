# AGENTS.md — AI Agent Guide for harbour-cloud-26

This file tells an AI agent everything it needs to work effectively in this repository.
Read it before making any changes.

---

## Repository snapshot

| Item | Value |
|---|---|
| **Language** | Java 25 |
| **Framework** | Spring Boot 4.0.6 (Spring MVC, not WebFlux) |
| **Build tool** | Gradle (Kotlin DSL) — always use `./gradlew`, never a system `gradle` |
| **Test framework** | JUnit 5 + Spring MockMvc (no Testcontainers, no Docker needed for tests) |
| **Storage** | In-memory `ConcurrentHashMap` — intentionally simple, no database yet |
| **Sidecar** | Toxiproxy via Docker Compose — started automatically by Spring Boot dev-tools |

---

## Running & verifying

```bash
# Compile and run all tests (no Docker required)
./gradlew test

# Start the application (Docker must be running — starts Toxiproxy sidecar)
./gradlew bootRun

# Full build
./gradlew build
```

After `bootRun` the app is available at:
- `http://localhost:8080` — direct
- `http://localhost:9091` — through Toxiproxy (network-fault injection)
- `http://localhost:8474` — Toxiproxy management API

**Always run `./gradlew test` after changes and confirm it passes before declaring a task done.**

---

## Architecture in one paragraph

`PaymentController` accepts REST requests and delegates to `PaymentService`, which implements idempotent registration: it builds a `Payment` record and calls `PaymentRepository.saveIfAbsent`, which uses a `ConcurrentHashMap` keyed on `(storeId, idempotencyKey)` to atomically store-or-return. The service returns a `RegistrationResult` that carries a `created` flag; the controller maps `true → 201` and `false → 200`. Validation is done by Jakarta Bean Validation annotations on `PaymentRequest` and by `@NotBlank` on controller headers; `PaymentExceptionHandler` converts failures into RFC-9457 `ProblemDetail` responses.

---

## Package & file map

```
src/main/java/space/harbour/cloud/
├── CloudApplication.java          # @SpringBootApplication entry point — do not modify
└── payments/
    ├── CoffeeType.java             # Enum — add new coffee variants here
    ├── Payment.java                # Immutable domain record (no setters)
    ├── PaymentRequest.java         # JSON body + Bean Validation constraints
    ├── PaymentResponse.java        # API projection of Payment
    ├── PaymentController.java      # REST layer — headers, routing, status codes
    ├── PaymentService.java         # Business logic, idempotency
    ├── PaymentRepository.java      # In-memory persistence
    ├── PaymentConfig.java          # Spring @Configuration — Clock bean
    └── PaymentExceptionHandler.java# @RestControllerAdvice for 400s
```

---

## Key invariants (do not break)

1. **Idempotency** — `PaymentRepository.saveIfAbsent` must remain atomic. If you change storage, preserve the `putIfAbsent` semantic.
2. **`created` flag** — `PaymentService.RegistrationResult.created()` must be `true` only on the first successful write. `PaymentController` relies on it for status codes.
3. **`Payment` is immutable** — it is a Java `record`; do not convert it to a mutable class.
4. **No Spring Security** — there is no auth layer; do not add it without a matching task.
5. **No database yet** — the in-memory store is deliberate (course progression). Do not add JPA/JDBC unless the task explicitly asks for it.

---

## How to add a new endpoint

1. Add any new request/response records to the `payments` package (follow the existing `PaymentRequest` / `PaymentResponse` pattern).
2. Add the handler method to `PaymentController` with proper `@RequestMapping` and Javadoc.
3. Add service logic to `PaymentService` (or a new service); update `PaymentRepository` if new queries are needed.
4. Add a `@SpringBootTest` + MockMvc test in `PaymentControllerTest` covering at least the happy path and one validation failure.
5. Run `./gradlew test`.

---

## How to add a new `CoffeeType`

Add the constant to `CoffeeType.java`. No other changes are required — the enum is serialised as its name by default Jackson config.

---

## Testing conventions

- All tests live under `src/test/java/space/harbour/cloud/`.
- Use `@SpringBootTest` + `MockMvcBuilders.webAppContextSetup` (see `PaymentControllerTest`).
- Spin up a fresh `MockMvc` per test method to avoid shared state from the in-memory repository.
- Test names follow `<scenario><ExpectedOutcome>()` camelCase, e.g. `replayingSameIdempotencyKeyReturnsSamePaymentWith200`.
- No Mockito stubs for repository/service in controller tests — use the real implementation (fast enough in-memory).

---

## Toxiproxy / Docker Compose

`compose.yaml` defines a single `toxiproxy` service that proxies port `9091 → host.docker.internal:8080`.
`toxiproxy.json` seeds the proxy configuration.

**Do not change port 9091 or 8080** — `application.properties` documents them and tests reference them.

To temporarily disable Toxiproxy for local debugging, set the env var:
```
SPRING_DOCKER_COMPOSE_ENABLED=false ./gradlew bootRun
```

---

## Common agent pitfalls

| Pitfall | What to do instead |
|---|---|
| Editing `build/` artefacts | Only edit files under `src/` and root config files |
| Using `gradle` directly | Always use `./gradlew` |
| Adding `return` to a record accessor | Records generate accessors automatically; just call `payment.paymentId()` |
| Importing `javax.validation` | This project uses `jakarta.validation` (Spring Boot 3+/4+) |
| Assuming a database | Storage is a `ConcurrentHashMap`; no JDBC/JPA is present |
| Breaking existing tests | Run `./gradlew test` and fix failures before finishing |
