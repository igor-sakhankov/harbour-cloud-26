# Offline Payments Upload Script

Reads a CSV of coffee payments collected offline and posts them to the StarHarbour Payments API with automatic retries and idempotency guarantees.

## Prerequisites

```bash
pip install requests
```

## CSV format

| Column           | Required | Notes                                                                                     |
|------------------|----------|-------------------------------------------------------------------------------------------|
| `store_id`       | yes      |                                                                                           |
| `transaction_id` | no       | Used as `Idempotency-Key`. Auto-generated (MD5 of row content + index) if blank.          |
| `coffee_type`    | yes      | Must match API enum: `ESPRESSO`, `DOUBLE_ESPRESSO`, `AMERICANO`, `LATTE`, `CAPPUCCINO`, `FLAT_WHITE`, `MOCHA`, `CORTADO`, `MACCHIATO`, `COLD_BREW` |
| `price`          | yes      | Positive decimal, ≤ 2 decimal places                                                      |
| `currency`       | yes      | 3-letter ISO-4217 code, e.g. `EUR`                                                        |
| `loyalty_card_id`| no       | Leave blank if none                                                                       |

## Basic usage

```bash
# Against the real app (default)
python upload_payments.py sample_payments.csv

# Against the Toxiproxy fault-injection port
python upload_payments.py sample_payments.csv --url http://localhost:9091/api/v1/payments
```

---

## Test Plan

### 1. Happy Path

Start the app (`./gradlew bootRun` from the project root), then run:

```bash
python upload_payments.py sample_payments.csv
```

**Expected output:**
- Rows 1–10: `[CREATED]` with a new `paymentId` each
- Row 11 (`INVALID_COFFEE`): `[SKIP]` — caught by local validation before any HTTP call
- Summary: `10/11 processed successfully, 1 failed.`

---

### 2. Idempotent Replay

Run the **exact same** command a second time without restarting the app:

```bash
python upload_payments.py sample_payments.csv
```

**Expected output:**
- All previously-created rows: `[EXISTS ]` — server returned `200 OK`, no duplicates
- Row 11: `[SKIP]` again
- Summary: `10/11 processed successfully, 1 failed.`

This proves the `Idempotency-Key` header works end-to-end and rerunning is always safe.

---

### 3. Chaos Testing (Toxiproxy)

This test verifies the exponential-backoff retry logic survives real network faults.

**Step 1 — Restart the app** (clears in-memory store so we get fresh `201` responses):
```bash
# Ctrl-C the running bootRun, then:
./gradlew bootRun
```

**Step 2 — Inject a latency/timeout toxic** via the Toxiproxy management API:
```bash
# Add a 6-second latency with 100% jitter (effectively a timeout for our 10s limit)
curl -s -X POST http://localhost:8474/proxies/spring-boot-app/toxics \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "latency-fault",
    "type": "latency",
    "stream": "downstream",
    "toxicity": 1.0,
    "attributes": { "latency": 6000, "jitter": 0 }
  }' | python3 -m json.tool
```

**Step 3 — Run the script through the proxy port**:
```bash
python upload_payments.py sample_payments.csv --url http://localhost:9091/api/v1/payments
```

**Expected output:** Each row shows `[attempt N/5] ... retrying in X.Xs...` before eventually succeeding (the 6 s delay is within the 10 s timeout, so requests succeed slowly).

**Step 4 — Inject a connection-reset toxic** (harder failure):
```bash
# Remove previous toxic first
curl -s -X DELETE http://localhost:8474/proxies/spring-boot-app/toxics/latency-fault

# Add a timeout toxic that cuts the connection after 100ms
curl -s -X POST http://localhost:8474/proxies/spring-boot-app/toxics \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "timeout-fault",
    "type": "timeout",
    "stream": "downstream",
    "toxicity": 1.0,
    "attributes": { "timeout": 100 }
  }' | python3 -m json.tool
```

Re-run the script (restart the app first to clear state):
```bash
python upload_payments.py sample_payments.csv --url http://localhost:9091/api/v1/payments
```

**Expected output:** Rows fail with `Timeout` / `ConnectionError`, script retries with backoff (`1s → 2s → 4s → 8s → 16s`), all 5 attempts exhausted, summary shows failures. This confirms the retry cap and fail-safe behaviour.

**Step 5 — Remove the toxic and verify recovery**:
```bash
curl -s -X DELETE http://localhost:8474/proxies/spring-boot-app/toxics/timeout-fault
```

Re-run once more to confirm the script succeeds again (idempotent replay gives `[EXISTS]` for any rows that snuck through during chaos):
```bash
python upload_payments.py sample_payments.csv --url http://localhost:9091/api/v1/payments
```

---

### 4. Validation Failure (400)

Add a row with a valid coffee type but a negative price to a test CSV:

```csv
store_id,transaction_id,coffee_type,price,currency,loyalty_card_id
store-alpha,txn-bad,-1.00,EUR,
```

Actually the local validator catches negative prices before the HTTP call. To exercise the server-side `400` path, temporarily set `price` to `0` which passes Python's `float` check but may fail server-side `@DecimalMin`:

```bash
echo "store_id,transaction_id,coffee_type,price,currency,loyalty_card_id
store-alpha,txn-zero-price,LATTE,0.00,EUR," > /tmp/bad_payment.csv

python upload_payments.py /tmp/bad_payment.csv
```

**Expected:** `[INVALID]` with the RFC-9457 `ProblemDetail` detail message, no retry.
