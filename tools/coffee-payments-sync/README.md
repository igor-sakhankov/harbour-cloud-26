# coffee-payments-sync

A small command-line tool that reads a CSV of a day's coffee sales and posts each
one to the payments API (`POST /api/v1/payments`). Plain Python 3, standard
library only, nothing to install.

The API runs behind Toxiproxy, so requests can be slow, dropped or time out. The
tool is built to cope with that without losing or duplicating payments:

- It sends a stable `Idempotency-Key` for every row, the same key on every retry.
  The server stores payments by `(Store-Id, Idempotency-Key)`, so if a response
  is lost and we retry, the server returns the original payment (`200`) instead
  of creating a second one. (If you don't send a key the server makes up a random
  one, which defeats this, so we always send our own.)
- Retryable failures (timeouts, connection errors, `429`, `5xx`) are retried with
  exponential backoff and a bit of jitter, up to `--max-retries`.
- A `400` is a validation problem that won't get better on retry, so we don't
  retry it; we print the server's message and move on.
- Confirmed rows are written to a small ledger file as we go. Run the same CSV
  again and already-sent rows are skipped, so a run that died halfway can just be
  restarted.

Rows are validated locally before anything is sent, and the process exits
non-zero if any row failed.

## Usage

```bash
cd tools/coffee-payments-sync

python3 -m coffee_sync --store-id STORE123 sample_payments.csv

# go through Toxiproxy to test against injected faults
python3 -m coffee_sync --store-id STORE123 --base-url http://localhost:9091 sample_payments.csv

# check the file without sending anything
python3 -m coffee_sync --store-id STORE123 --dry-run sample_payments.csv
```

## CSV format

First row is the header. `coffee_type`, `price`, `currency` and `loyalty_card_id`
are required. `store_id` and `idempotency_key` are optional overrides per row.

| Column | Required | Notes |
|---|---|---|
| `coffee_type` | yes | One of the CoffeeType values (case-insensitive). |
| `price` | yes | Positive, up to 2 decimals. |
| `currency` | yes | 3-letter code. |
| `loyalty_card_id` | yes | Non-empty. |
| `store_id` | no | Overrides `--store-id` for that row. |
| `idempotency_key` | no | Use your own key; otherwise one is derived from the row. |

## Options

| Flag | Default | Meaning |
|---|---|---|
| `--store-id` | required | Store-Id for rows that don't set their own. |
| `--base-url` | `http://localhost:8080` | API base URL; use `:9091` for Toxiproxy. |
| `--ledger` | `<csv>.ledger.jsonl` | Where the resume ledger is kept. |
| `--max-retries` | `5` | Attempts per row on retryable errors. |
| `--timeout` | `10` | Per-request timeout in seconds. |
| `--dry-run` | off | Validate only, no requests, no ledger. |

## Tests

```bash
cd tools/coffee-payments-sync
python3 -m unittest discover -s tests
```

The tests run a small fake server in-process that injects timeouts and `500`s to
cover the retry, replay, `400` and resume cases.
