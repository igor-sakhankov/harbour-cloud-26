# coffee-payments-sync

Reliably propagate a CSV of a day's coffee sales to the StarHarbour Central
System (`POST /api/v1/payments`). Pure Python 3 standard library — no install.

## Why it is reliable

The Central System deliberately injects network faults (latency, packet loss,
timeouts) via Toxiproxy. This tool survives them without losing or duplicating
payments:

- **Stable idempotency key per row** — sent as `Idempotency-Key` on every
  attempt. A retry after a lost response replays (`200`) instead of creating a
  duplicate. The server keys idempotency on `(Store-Id, Idempotency-Key)`; if
  the client omitted the key the server would generate a random one and dedup
  would break — so we always send our own.
- **Retry with exponential backoff + jitter** on timeouts, connection errors,
  `429` and `5xx`; bounded by `--max-retries`.
- **No retry on `400`** — validation errors can never succeed on replay; the
  server's message is reported and the row is skipped.
- **Resume ledger** — every confirmed payment is appended to an append-only
  JSONL ledger; re-running the same file skips already-confirmed rows, so a
  crashed or partial run can be safely re-run.

## Usage

```bash
cd tools/coffee-payments-sync

# against the direct port
python3 -m coffee_sync --store-id STORE123 sample_payments.csv

# against Toxiproxy (fault injection) to prove reliability
python3 -m coffee_sync --store-id STORE123 --base-url http://localhost:9091 sample_payments.csv

# see what would be sent without sending
python3 -m coffee_sync --store-id STORE123 --dry-run sample_payments.csv
```

Exit code is `0` when every row is confirmed, non-zero if any row failed.

## CSV format

Header row required. `coffee_type`, `price`, `currency`, `loyalty_card_id` are
required; `store_id` and `idempotency_key` are optional per-row overrides.

| Column | Required | Notes |
|---|---|---|
| `coffee_type` | yes | One of the `CoffeeType` enum values (case-insensitive). |
| `price` | yes | Positive, ≤ 2 decimal places. |
| `currency` | yes | 3-letter ISO-4217 code. |
| `loyalty_card_id` | yes | Non-empty. |
| `store_id` | no | Overrides `--store-id` for that row. |
| `idempotency_key` | no | Explicit stable key; otherwise derived from row content. |

## Options

| Flag | Default | Meaning |
|---|---|---|
| `--store-id` | (required) | Default `Store-Id` for rows without one. |
| `--base-url` | `http://localhost:8080` | Central System URL; use `:9091` for Toxiproxy. |
| `--ledger` | `<csv>.ledger.jsonl` | Resume ledger path. |
| `--max-retries` | `5` | Max attempts per row on retryable errors. |
| `--timeout` | `10` | Per-request timeout (seconds). |
| `--dry-run` | off | Parse and validate only; no network calls, no ledger writes. |

## Tests

```bash
cd tools/coffee-payments-sync
python3 -m unittest discover -s tests -v
```

Tests use an in-process fake Central System that injects timeouts and `500`s to
exercise retry, idempotent replay, `400` handling, and ledger-based resume.
