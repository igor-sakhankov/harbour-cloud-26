# Coffee Payments Sync — Design

**Date:** 2026-06-12
**Status:** Approved
**Author:** mkhlndrv

## Problem

You own a Coffee Place. Throughout the day you record every sale in a notebook.
At end of day those payments must be propagated to the StarHarbour Central
System (the `harbour-cloud-26` payments API). We need automation that takes a
CSV export of the day's sales and **reliably** registers every payment with the
Central System — reliably meaning: no lost sales and no double-charges, even
though the Central System deliberately injects network faults (latency, packet
loss, timeouts) via Toxiproxy.

This document specifies a standalone client CLI, `coffee-payments-sync`, that
lives in this fork and submits payments to the existing API. It does **not**
modify the Central System.

## The API contract (from source)

`POST /api/v1/payments`

- **Headers:** `Store-Id` (required, non-blank), `Idempotency-Key` (optional).
- **Body (JSON):**
  - `coffeeType` — one of the `CoffeeType` enum values: `ESPRESSO`,
    `DOUBLE_ESPRESSO`, `AMERICANO`, `LATTE`, `CAPPUCCINO`, `FLAT_WHITE`,
    `MOCHA`, `CORTADO`, `MACCHIATO`, `COLD_BREW`.
  - `price` — decimal `> 0`, at most 2 decimal places, ≤ 10 integer digits.
  - `currency` — 3-letter uppercase ISO-4217 code (`^[A-Z]{3}$`).
  - `loyaltyCardId` — required (non-null).
- **Responses:**
  - `201 Created` — new payment registered.
  - `200 OK` — idempotency key already seen; original payment echoed back.
  - `400 Bad Request` — validation failure, RFC-9457 `ProblemDetail` JSON with a
    human-readable `detail` field.

**Critical idempotency nuance:** the server keys idempotency on
`(Store-Id, Idempotency-Key)`. If the client omits `Idempotency-Key`, the
**server generates a random UUID**, so the request is *not* idempotent. Therefore
the client MUST send a stable `Idempotency-Key` per logical payment for retries
to dedupe. This is the core of "reliable".

## Goals / Non-goals

**Goals**
- Read a CSV of the day's payments and POST each to the Central System.
- Survive injected network faults without losing or duplicating payments.
- Be resumable: re-running after a crash/partial run finishes the remainder and
  never re-sends an already-confirmed payment.
- Report a clear per-run summary; exit non-zero on any permanent failure.
- Zero runtime dependencies — runs with `python3` alone.

**Non-goals (YAGNI)**
- Concurrency / parallel sends — end-of-day volume is small; sequential is
  simpler and easier to reason about.
- Modifying the Central System or adding a server-side import endpoint.
- A database/persistent queue — the resume ledger file is sufficient.
- Authentication — the API has none.

## Architecture

A standalone, zero-dependency Python 3 CLI placed in the fork at
`tools/coffee-payments-sync/`. Pure standard library (`csv`, `urllib`,
`hashlib`, `json`, `argparse`, `time`, `random`). Split into small,
independently testable units:

```
tools/coffee-payments-sync/
├── coffee_sync/
│   ├── __init__.py
│   ├── __main__.py     # CLI: arg parsing, orchestration, end-of-run report
│   ├── parser.py       # CSV row -> validated PaymentRow | RowError
│   ├── client.py       # HTTP POST with retry/backoff + idempotency
│   └── ledger.py       # append-only JSONL resume ledger
├── tests/
│   ├── test_parser.py
│   ├── test_client.py      # uses a stdlib fake HTTP server (fault injection)
│   ├── test_ledger.py
│   └── test_end_to_end.py
├── sample_payments.csv
└── README.md
```

Each unit has one job and a narrow interface:

- **parser** — `parse_csv(path, default_store_id) -> (rows, errors)`. Pure;
  no I/O beyond reading the file. Validates every field against the API contract
  *before* any network call, so malformed rows fail fast and locally.
- **client** — `PaymentClient(base_url, timeout, max_retries).register(row)
  -> Result(status, payment_id, created|replayed)`. Owns retry/backoff and the
  idempotency header. Knows nothing about CSV or the ledger.
- **ledger** — `Ledger(path)` with `confirmed_keys() -> set[str]` and
  `record(key, payment_id, status)`. Append-only; the only stateful file.
- **__main__** — wires them: parse → skip already-confirmed → send → record →
  summarize.

## CSV format

Header row required. Columns:

| Column            | Required | Notes |
|-------------------|----------|-------|
| `coffee_type`     | yes      | Must match a `CoffeeType` value (case-insensitive in, upper-cased out). |
| `price`           | yes      | Positive, ≤ 2 decimals. |
| `currency`        | yes      | 3-letter code; upper-cased. |
| `loyalty_card_id` | yes      | Non-empty. |
| `store_id`        | no       | Overrides the global `--store-id` for this row. |
| `idempotency_key` | no       | Explicit stable key; otherwise derived (below). |

A sample `sample_payments.csv` ships with the tool.

## Idempotency key derivation

Per row:
1. If the `idempotency_key` column is present and non-empty → use it verbatim.
2. Otherwise derive deterministically:
   `sha256(store_id | coffee_type | price | currency | loyalty_card_id | row_number)`,
   hex-encoded (optionally truncated). Including the 1-based `row_number` keeps
   two genuinely identical sales distinct, while keeping the key **stable across
   re-runs of the same file** so retries and resumes dedupe correctly.

## Reliability layer (`client.py`)

- Set the stable `Idempotency-Key` header on **every** attempt for a row.
- **Success:** `201` → counted as `created`; `200` → counted as `replayed`
  (already existed server-side). Both are "confirmed" and written to the ledger.
- **Retry** on: connection errors, timeouts, `5xx`, `429`. Strategy: exponential
  backoff `base * 2**attempt` plus random jitter, capped at a max delay, bounded
  by `--max-retries` attempts.
- **Do not retry** `400`: this is a validation error and will never succeed on
  replay. Capture the server's `ProblemDetail.detail` text, mark the row
  `failed`, and continue with the next row.
- Other unexpected `4xx` → treated as permanent failure for that row (no retry),
  recorded with the response body.
- If retries are exhausted on a retryable error → row marked `failed` with the
  last error; the run continues and exits non-zero at the end.

Because the idempotency key is stable, the classic lost-response hazard is safe:
if attempt N actually reached the server but the response was dropped, attempt
N+1 returns `200` with the same payment rather than creating a duplicate.

## Resume ledger (`ledger.py`)

- Append-only JSONL sidecar file. Default path: `<csv-basename>.ledger.jsonl`
  next to the CSV; overridable with `--ledger`.
- Each confirmed row appends one line:
  `{"idempotency_key": "...", "payment_id": "...", "status": "created|replayed"}`.
- On startup the ledger is read into a set of confirmed keys. Any row whose
  idempotency key is already confirmed is **skipped** (counted as `skipped`).
- Append-only + flush-per-line keeps it crash-safe: a kill mid-run loses at most
  the in-flight row, which the stable idempotency key makes safe to resend.

## CLI

```
python3 -m coffee_sync --store-id STORE123 payments.csv \
    [--base-url http://localhost:8080] \
    [--ledger PATH] \
    [--max-retries 5] \
    [--timeout 10] \
    [--dry-run]
```

- `--store-id` (required) — default store id for rows without `store_id`.
- `--base-url` — Central System base URL. Default `http://localhost:8080`
  (direct). Point at `http://localhost:9091` to exercise Toxiproxy faults.
- `--ledger` — resume ledger path.
- `--max-retries` — max attempts per row on retryable errors.
- `--timeout` — per-request timeout (seconds).
- `--dry-run` — parse, validate, and report what *would* be sent; no network
  calls, no ledger writes.

## Reporting & exit code

No silent failures — every row ends in exactly one terminal state:
`created`, `replayed`, `skipped` (ledger), or `failed`. At the end print a
summary:

```
Processed 42 rows: 38 created, 2 replayed, 1 skipped, 1 failed
Failures:
  row 17: 400 price must be greater than zero
```

Exit `0` if no failures, non-zero otherwise — so it is usable from cron/CI.

## Error handling philosophy

- Validate locally before sending; never let a malformed row trigger a network
  call that is guaranteed to 400.
- Distinguish *retryable* (network/5xx/429) from *permanent* (4xx) precisely.
- Surface every failure in the final report with the server's own message;
  never swallow an error.

## Testing strategy

- **parser** — valid rows; each invalid case (unknown `coffee_type`, non-numeric
  / zero / negative / >2-decimal `price`, bad `currency`, empty `loyalty_card_id`,
  missing required column); per-row `store_id` override.
- **idempotency** — same row + same file → identical derived key; explicit
  `idempotency_key` column wins; different `row_number` → different key.
- **client** — a stdlib `http.server` fake that:
  - returns `201`, then `200` on replay of the same key (idempotency);
  - injects K timeouts / `500`s before succeeding (proves retry + backoff);
  - returns `400` for a bad payload (proves no-retry + message capture).
- **ledger** — round-trip read/write; corrupted/partial last line tolerated.
- **end-to-end** — run over a small CSV against the fake server, kill/restart
  semantics simulated by pre-seeding the ledger, assert no row is re-sent and the
  summary/exit code are correct.

## Deliverable

A pull request from `mkhlndrv/harbour-cloud-26:feature/csv-payments-sync` adding
the `tools/coffee-payments-sync/` tool, this design doc, a README, and tests.
The PR description explains the reliability model (idempotency + retry + resume)
and how to run it against the Toxiproxy port to demonstrate fault tolerance.
