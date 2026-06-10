# CSV Payment Uploader

A Python script that reads end-of-day coffee payments from a CSV file and
reliably sends them to the StarHarbour Central Payments API.

## Files

| File | Purpose |
|---|---|
| `uploader.py` | Main script — reads CSV and POSTs to the API |
| `payments.csv` | Sample CSV with 8 coffee orders |
| `test_uploader.py` | Unit tests (no live server needed) |
| `sent_orders.json` | Auto-created — tracks already-sent orders |

## Requirements

- Python 3.8+ (no third-party packages needed — uses only the standard library)
- The StarHarbour API running locally (see root README)

## How to run

### 1. Start the API
```bash
# From the repo root
./gradlew bootRun
```

### 2. Upload payments
```bash
cd submissions/csv-uploader
python uploader.py
```

Optional flags:
```bash
python uploader.py --file my_payments.csv   # custom CSV
python uploader.py --url http://host:8080   # different server
python uploader.py --store my-store-id      # different store
```

### 3. Run tests (no server needed)
```bash
python -m pytest test_uploader.py -v
```

## CSV format

```csv
order_id,coffee_type,price,currency,loyalty_card_id
order-001,LATTE,3.50,EUR,card-001
```

Valid `coffee_type` values: `ESPRESSO`, `DOUBLE_ESPRESSO`, `AMERICANO`, `LATTE`,
`CAPPUCCINO`, `FLAT_WHITE`, `MOCHA`, `CORTADO`, `MACCHIATO`, `COLD_BREW`

`currency` must be a 3-letter ISO-4217 code, e.g. `EUR`, `USD`, `GBP`

## Reliability design

| Feature | How it works |
|---|---|
| **Idempotency** | Each row's `order_id` is sent as the `Idempotency-Key` header — re-running the script never creates duplicates |
| **Retry + back-off** | Up to 3 attempts per order; waits 1 s → 2 s → 4 s between retries |
| **Sent tracking** | Successfully uploaded order IDs are saved to `sent_orders.json` — already-sent rows are skipped on reruns |
| **Client error handling** | 4xx responses (bad data) are not retried — they are logged and skipped |
