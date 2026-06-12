# Coffee Payments Sync

Small Python automation for sending Coffee Place CSV payments to the StarHarbour central payments service.

The target API is `POST /api/v1/payments` with:

- `Store-Id` header from `store_id`
- `Idempotency-Key` header from `idempotency_key`, or from `transaction_id` / `payment_id` / `order_id` / `reference`
- JSON body fields `coffeeType`, `price`, `currency`, and `loyaltyCardId`

## CSV Format

Required columns:

```csv
store_id,coffee_type,price,currency,loyalty_card_id
store-bkk-01,LATTE,3.50,EUR,card-123
```

Recommended column:

```csv
transaction_id
```

A stable transaction id is the safest idempotency source. If the CSV has neither `idempotency_key` nor a transaction/reference column, the tool derives a deterministic key from the CSV filename, line number, and row contents.

## Usage

Run the central service, then:

```bash
python3 coffee_payments_sync.py sample_payments.csv --base-url http://localhost:8080
```

Useful options:

```bash
python3 coffee_payments_sync.py payments.csv --dry-run
python3 coffee_payments_sync.py payments.csv --base-url http://localhost:9091
python3 coffee_payments_sync.py payments.csv --state-file payments.state.json
python3 coffee_payments_sync.py --list-coffee-types
```

The sync journal defaults to `payments.csv.sync-state.json`. Successful rows are recorded after every API response, so rerunning the same command resumes unfinished work and skips completed rows.

## Reliability Behavior

- Retries network errors, timeouts, HTTP `408`, `425`, `429`, and `5xx`.
- Reuses the same idempotency key on every retry.
- Treats both `201 Created` and `200 OK` as success.
- Stops retrying validation/client errors such as `400 Bad Request`.

## Tests

```bash
python3 -m unittest -v
```
