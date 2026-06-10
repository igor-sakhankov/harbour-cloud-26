# Reliable CSV Payment Importer

End-of-day automation for the Coffee Place: read the day's payments from a CSV
"notebook" and push every row into the StarHarbour **Payments API** — reliably,
even when the network misbehaves.

This is the *client* side of the assignment. It does not modify the server; it
talks to it over HTTP through the Toxiproxy port so it can be tested under
injected latency and connection faults.

## Files

| File | Purpose |
|---|---|
| `payments.csv` | Sample end-of-day ledger (30 valid rows + 3 deliberately invalid). |
| `generate_csv.py` | Regenerate `payments.csv` with [Faker](https://faker.readthedocs.io/). |
| `import_payments.py` | CLI importer — takes a CSV path, sends it reliably. |
| `reliable_payment_importer.ipynb` | Same logic as a notebook, plus verification + charts. |
| `requirements.txt` | Python dependencies. |

## CSV format

```
order_id,store_id,coffee_type,price,currency,loyalty_card_id
```

- `order_id` — unique per ledger line; used as the **Idempotency-Key** (so retries are safe).
- `coffee_type` — one of the server `CoffeeType` enum (`LATTE`, `ESPRESSO`, …).
- `price` — `> 0`, at most 2 decimals.
- `currency` — 3-letter ISO-4217 code (`EUR`/`GBP`/`USD`).
- `store_id`, `loyalty_card_id` — free text, required.

## Reliability strategy

| Concern | Approach |
|---|---|
| Lost requests (timeout, reset, 5xx) | Retry with **exponential backoff + jitter** (`MAX_RETRIES=5`). |
| Duplicate writes after a retry | Stable per-row **`Idempotency-Key`** → server replies `201` once, `200` on replays. |
| Bad data | `400` is **non-retryable** — fail fast, report, move on. |
| Proving correctness | Read the ledger back via `GET /payments?storeId=` and assert **no duplicates**. |

The client always posts through `http://localhost:9091` (Toxiproxy), so every
request experiences whatever network conditions are injected.

## Run it

1. Start the server (from the repo root):

   ```bash
   ./gradlew bootRun
   ```

   App on `:8080`, Toxiproxy proxy on `:9091`, Toxiproxy admin on `:8474`.

2. Set up Python and launch the notebook:

   ```bash
   cd client
   python3 -m venv .venv && source .venv/bin/activate   # bash/zsh
   # fish: source .venv/bin/activate.fish
   pip install -r requirements.txt
   jupyter notebook reliable_payment_importer.ipynb
   ```

3. Run the cells top to bottom. The notebook:
   - sends the ledger over a healthy network (Run 1),
   - injects latency + 35% connection resets and resends the *same* CSV (Run 2),
   - asserts the server payment count is unchanged (exactly-once),
   - plots the business data and the retry behaviour.

## Run it as a script (no notebook)

Same reliability logic, takes the CSV path as an argument:

```bash
cd client
pip install -r requirements.txt

# minimal: send a CSV through the Toxiproxy port
python import_payments.py payments.csv

# read the ledger back and assert exactly-once; bypass the proxy with --base-url
python import_payments.py payments.csv --verify
python import_payments.py payments.csv --base-url http://localhost:8080 --verify

# also write summary charts to a PNG
python import_payments.py payments.csv --verify --charts summary.png
```

Exit code is non-zero if any row exhausts its retries (network failure) or if
verification finds duplicates — handy for CI. Validation `400`s are reported but
do not fail the run (bad data is expected, not a delivery failure).

To regenerate the sample data:

```bash
python generate_csv.py --rows 40 --out payments.csv
```
