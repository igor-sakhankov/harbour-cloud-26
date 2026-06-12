# Coffee Payments Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `coffee-payments-sync`, a zero-dependency Python 3 CLI that reads a CSV of a day's coffee sales and reliably registers each with the StarHarbour payments API, surviving injected network faults without losing or duplicating payments.

**Architecture:** A standalone client in `tools/coffee-payments-sync/`, split into four small units — `parser` (CSV → validated rows), `client` (HTTP POST with retry/backoff + stable idempotency key), `ledger` (append-only JSONL resume state), and `__main__` (orchestration + reporting). Pure Python standard library; runs with `python3` alone.

**Tech Stack:** Python 3 stdlib only — `csv`, `urllib.request`, `hashlib`, `json`, `argparse`, `time`, `random`, `dataclasses`. Tests use `unittest` + a stdlib `http.server` fake for fault injection.

---

## File Structure

```
tools/coffee-payments-sync/
├── coffee_sync/
│   ├── __init__.py     # package marker + version
│   ├── parser.py       # PaymentRow, RowError, parse_csv(), idempotency_key()
│   ├── client.py       # PaymentClient, SendResult, retry/backoff
│   ├── ledger.py       # Ledger: confirmed_keys(), record()
│   └── __main__.py     # CLI: argparse, orchestration, summary, exit code
├── tests/
│   ├── __init__.py
│   ├── _fake_server.py     # reusable stdlib fake Central System
│   ├── test_parser.py
│   ├── test_ledger.py
│   ├── test_client.py
│   └── test_end_to_end.py
├── sample_payments.csv
└── README.md
```

Each unit has one responsibility and a narrow interface; `__main__` is the only place they are wired together. Tests run from the `tools/coffee-payments-sync/` directory so `coffee_sync` is importable as a package.

---

## Task 1: Package skeleton

**Files:**
- Create: `tools/coffee-payments-sync/coffee_sync/__init__.py`
- Create: `tools/coffee-payments-sync/tests/__init__.py`

- [ ] **Step 1: Create the package marker**

`tools/coffee-payments-sync/coffee_sync/__init__.py`:
```python
"""coffee-payments-sync: reliably propagate a CSV of coffee sales to the
StarHarbour Central System."""

__version__ = "1.0.0"
```

- [ ] **Step 2: Create the tests package marker**

`tools/coffee-payments-sync/tests/__init__.py`:
```python
```
(empty file)

- [ ] **Step 3: Verify the package imports**

Run (from `tools/coffee-payments-sync/`): `python3 -c "import coffee_sync; print(coffee_sync.__version__)"`
Expected: prints `1.0.0`

- [ ] **Step 4: Commit**

```bash
git add tools/coffee-payments-sync/coffee_sync/__init__.py tools/coffee-payments-sync/tests/__init__.py
git commit -m "feat(sync): package skeleton"
```

---

## Task 2: CSV parser + validation

Implements the CSV format and per-field validation against the API contract,
plus the deterministic idempotency-key derivation.

**Files:**
- Create: `tools/coffee-payments-sync/coffee_sync/parser.py`
- Test: `tools/coffee-payments-sync/tests/test_parser.py`

- [ ] **Step 1: Write the failing tests**

`tools/coffee-payments-sync/tests/test_parser.py`:
```python
import io
import unittest

from coffee_sync.parser import (
    PaymentRow,
    RowError,
    parse_rows,
    idempotency_key,
)


def rows_from(text, default_store_id="STORE1"):
    return parse_rows(io.StringIO(text), default_store_id=default_store_id)


VALID = (
    "coffee_type,price,currency,loyalty_card_id\n"
    "LATTE,3.50,EUR,card-1\n"
)


class ParseRowsTest(unittest.TestCase):
    def test_valid_row_parses(self):
        rows, errors = rows_from(VALID)
        self.assertEqual(errors, [])
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row.coffee_type, "LATTE")
        self.assertEqual(row.price, "3.50")
        self.assertEqual(row.currency, "EUR")
        self.assertEqual(row.loyalty_card_id, "card-1")
        self.assertEqual(row.store_id, "STORE1")
        self.assertEqual(row.row_number, 2)  # header is line 1

    def test_coffee_type_is_uppercased_and_validated(self):
        rows, errors = rows_from(
            "coffee_type,price,currency,loyalty_card_id\nlatte,3.50,EUR,c\n"
        )
        self.assertEqual(errors, [])
        self.assertEqual(rows[0].coffee_type, "LATTE")

    def test_unknown_coffee_type_is_error(self):
        rows, errors = rows_from(
            "coffee_type,price,currency,loyalty_card_id\nTEA,3.50,EUR,c\n"
        )
        self.assertEqual(rows, [])
        self.assertEqual(len(errors), 1)
        self.assertIn("coffee_type", errors[0].message)

    def test_currency_is_uppercased(self):
        rows, _ = rows_from(
            "coffee_type,price,currency,loyalty_card_id\nLATTE,3.50,eur,c\n"
        )
        self.assertEqual(rows[0].currency, "EUR")

    def test_bad_currency_is_error(self):
        _, errors = rows_from(
            "coffee_type,price,currency,loyalty_card_id\nLATTE,3.50,EURO,c\n"
        )
        self.assertIn("currency", errors[0].message)

    def test_price_must_be_positive(self):
        _, errors = rows_from(
            "coffee_type,price,currency,loyalty_card_id\nLATTE,0,EUR,c\n"
        )
        self.assertIn("price", errors[0].message)

    def test_price_rejects_three_decimals(self):
        _, errors = rows_from(
            "coffee_type,price,currency,loyalty_card_id\nLATTE,3.555,EUR,c\n"
        )
        self.assertIn("price", errors[0].message)

    def test_price_rejects_non_numeric(self):
        _, errors = rows_from(
            "coffee_type,price,currency,loyalty_card_id\nLATTE,abc,EUR,c\n"
        )
        self.assertIn("price", errors[0].message)

    def test_empty_loyalty_card_is_error(self):
        _, errors = rows_from(
            "coffee_type,price,currency,loyalty_card_id\nLATTE,3.50,EUR,\n"
        )
        self.assertIn("loyalty_card_id", errors[0].message)

    def test_missing_required_column_is_error(self):
        _, errors = rows_from("coffee_type,price,currency\nLATTE,3.50,EUR\n")
        self.assertEqual(len(errors), 1)
        self.assertIn("loyalty_card_id", errors[0].message)

    def test_per_row_store_id_overrides_default(self):
        rows, _ = rows_from(
            "store_id,coffee_type,price,currency,loyalty_card_id\n"
            "STORE9,LATTE,3.50,EUR,c\n"
        )
        self.assertEqual(rows[0].store_id, "STORE9")

    def test_blank_store_id_falls_back_to_default(self):
        rows, _ = rows_from(
            "store_id,coffee_type,price,currency,loyalty_card_id\n"
            ",LATTE,3.50,EUR,c\n"
        )
        self.assertEqual(rows[0].store_id, "STORE1")

    def test_errors_do_not_stop_later_valid_rows(self):
        rows, errors = rows_from(
            "coffee_type,price,currency,loyalty_card_id\n"
            "TEA,3.50,EUR,c\n"
            "LATTE,2.00,EUR,c\n"
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(len(errors), 1)
        self.assertEqual(rows[0].row_number, 3)
        self.assertEqual(errors[0].row_number, 2)


class IdempotencyKeyTest(unittest.TestCase):
    def _row(self, **kw):
        base = dict(
            store_id="S", coffee_type="LATTE", price="3.50",
            currency="EUR", loyalty_card_id="c", row_number=2,
            idempotency_key="",
        )
        base.update(kw)
        return PaymentRow(**base)

    def test_explicit_key_wins(self):
        row = self._row(idempotency_key="explicit-123")
        self.assertEqual(idempotency_key(row), "explicit-123")

    def test_derived_key_is_deterministic(self):
        self.assertEqual(idempotency_key(self._row()), idempotency_key(self._row()))

    def test_different_row_number_changes_key(self):
        self.assertNotEqual(
            idempotency_key(self._row(row_number=2)),
            idempotency_key(self._row(row_number=3)),
        )

    def test_different_content_changes_key(self):
        self.assertNotEqual(
            idempotency_key(self._row(price="3.50")),
            idempotency_key(self._row(price="4.00")),
        )


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from `tools/coffee-payments-sync/`): `python3 -m unittest tests.test_parser -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'coffee_sync.parser'`

- [ ] **Step 3: Write the parser implementation**

`tools/coffee-payments-sync/coffee_sync/parser.py`:
```python
"""Parse and validate the day's coffee-sales CSV against the Central System's
payment contract. Validation happens here, before any network call, so a
malformed row never triggers a request that is guaranteed to 400."""

from __future__ import annotations

import csv
import hashlib
import re
from dataclasses import dataclass

COFFEE_TYPES = frozenset({
    "ESPRESSO", "DOUBLE_ESPRESSO", "AMERICANO", "LATTE", "CAPPUCCINO",
    "FLAT_WHITE", "MOCHA", "CORTADO", "MACCHIATO", "COLD_BREW",
})

REQUIRED_COLUMNS = ("coffee_type", "price", "currency", "loyalty_card_id")

_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
_PRICE_RE = re.compile(r"^\d{1,10}(\.\d{1,2})?$")


@dataclass(frozen=True)
class PaymentRow:
    store_id: str
    coffee_type: str
    price: str
    currency: str
    loyalty_card_id: str
    row_number: int
    idempotency_key: str


@dataclass(frozen=True)
class RowError:
    row_number: int
    message: str


def parse_rows(handle, default_store_id):
    """Read CSV from a text handle. Returns (rows, errors). Each input data row
    becomes exactly one PaymentRow or one RowError; parsing never stops early."""
    reader = csv.DictReader(handle)
    missing = [c for c in REQUIRED_COLUMNS if c not in (reader.fieldnames or [])]

    rows, errors = [], []
    # csv line numbers: header is line 1, first data row is line 2.
    for index, raw in enumerate(reader, start=2):
        if missing:
            errors.append(RowError(index, f"missing required column(s): {', '.join(missing)}"))
            continue
        row, error = _build_row(raw, index, default_store_id)
        (rows if error is None else errors).append(row if error is None else error)
    return rows, errors


def _build_row(raw, index, default_store_id):
    coffee_type = (raw.get("coffee_type") or "").strip().upper()
    if coffee_type not in COFFEE_TYPES:
        return None, RowError(index, f"coffee_type '{coffee_type}' is not a known CoffeeType")

    price = (raw.get("price") or "").strip()
    if not _PRICE_RE.match(price) or float(price) <= 0:
        return None, RowError(index, f"price '{price}' must be > 0 with at most 2 decimals")

    currency = (raw.get("currency") or "").strip().upper()
    if not _CURRENCY_RE.match(currency):
        return None, RowError(index, f"currency '{currency}' must be a 3-letter code")

    loyalty_card_id = (raw.get("loyalty_card_id") or "").strip()
    if not loyalty_card_id:
        return None, RowError(index, "loyalty_card_id is required")

    store_id = (raw.get("store_id") or "").strip() or default_store_id
    if not store_id:
        return None, RowError(index, "store_id is required (no --store-id given)")

    return PaymentRow(
        store_id=store_id,
        coffee_type=coffee_type,
        price=price,
        currency=currency,
        loyalty_card_id=loyalty_card_id,
        row_number=index,
        idempotency_key=(raw.get("idempotency_key") or "").strip(),
    ), None


def idempotency_key(row):
    """Stable key for a logical payment. Explicit column wins; otherwise derive
    deterministically from content + row number so identical sales stay distinct
    yet re-runs of the same file reproduce the same key."""
    if row.idempotency_key:
        return row.idempotency_key
    material = "|".join([
        row.store_id, row.coffee_type, row.price,
        row.currency, row.loyalty_card_id, str(row.row_number),
    ])
    return hashlib.sha256(material.encode("utf-8")).hexdigest()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_parser -v`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add tools/coffee-payments-sync/coffee_sync/parser.py tools/coffee-payments-sync/tests/test_parser.py
git commit -m "feat(sync): CSV parser, validation and idempotency key"
```

---

## Task 3: Resume ledger

Append-only JSONL store of confirmed payments so re-runs skip already-sent rows.

**Files:**
- Create: `tools/coffee-payments-sync/coffee_sync/ledger.py`
- Test: `tools/coffee-payments-sync/tests/test_ledger.py`

- [ ] **Step 1: Write the failing tests**

`tools/coffee-payments-sync/tests/test_ledger.py`:
```python
import os
import tempfile
import unittest

from coffee_sync.ledger import Ledger


class LedgerTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "run.ledger.jsonl")

    def test_empty_when_file_absent(self):
        self.assertEqual(Ledger(self.path).confirmed_keys(), set())

    def test_record_then_reload(self):
        Ledger(self.path).record("k1", "pay-1", "created")
        self.assertEqual(Ledger(self.path).confirmed_keys(), {"k1"})

    def test_multiple_records_accumulate(self):
        led = Ledger(self.path)
        led.record("k1", "pay-1", "created")
        led.record("k2", "pay-2", "replayed")
        self.assertEqual(Ledger(self.path).confirmed_keys(), {"k1", "k2"})

    def test_corrupt_trailing_line_is_ignored(self):
        with open(self.path, "w", encoding="utf-8") as fh:
            fh.write('{"idempotency_key": "k1", "payment_id": "p", "status": "created"}\n')
            fh.write("{ this is not valid json")  # e.g. a crash mid-write
        self.assertEqual(Ledger(self.path).confirmed_keys(), {"k1"})


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_ledger -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'coffee_sync.ledger'`

- [ ] **Step 3: Write the ledger implementation**

`tools/coffee-payments-sync/coffee_sync/ledger.py`:
```python
"""Append-only JSONL ledger of confirmed payments. Enables safe resume: a row
whose idempotency key is already recorded is skipped on the next run. Append +
flush per line keeps it crash-safe — at most the in-flight line is lost, and the
stable idempotency key makes resending that row safe."""

from __future__ import annotations

import json
import os


class Ledger:
    def __init__(self, path):
        self.path = path

    def confirmed_keys(self):
        """Set of idempotency keys already confirmed. Tolerates a corrupt final
        line from a crash mid-write by skipping unparseable lines."""
        keys = set()
        if not os.path.exists(self.path):
            return keys
        with open(self.path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    keys.add(json.loads(line)["idempotency_key"])
                except (ValueError, KeyError):
                    continue
        return keys

    def record(self, idempotency_key, payment_id, status):
        """Append one confirmed payment and flush to disk immediately."""
        entry = {
            "idempotency_key": idempotency_key,
            "payment_id": payment_id,
            "status": status,
        }
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_ledger -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tools/coffee-payments-sync/coffee_sync/ledger.py tools/coffee-payments-sync/tests/test_ledger.py
git commit -m "feat(sync): append-only resume ledger"
```

---

## Task 4: Fake Central System for tests

A reusable in-process HTTP server that mimics the real API and can inject faults.
Built before the client so client tests have something to talk to.

**Files:**
- Create: `tools/coffee-payments-sync/tests/_fake_server.py`

- [ ] **Step 1: Write the fake server**

`tools/coffee-payments-sync/tests/_fake_server.py`:
```python
"""In-process fake of the StarHarbour payments API for tests.

Mimics the real contract:
- POST /api/v1/payments with Store-Id + optional Idempotency-Key headers.
- 201 on first sight of (storeId, idempotencyKey); 200 replay afterwards.
- 400 ProblemDetail when the JSON body fails a basic check.

Fault injection: `fail_times` makes the next N requests fail before any succeed,
either by HTTP 500 or by sleeping past the client timeout.
"""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class FakeCentral:
    def __init__(self, fail_times=0, fail_mode="500", fail_delay=2.0):
        self.payments = {}          # (storeId, idemKey) -> paymentId
        self.requests_seen = 0      # every POST attempt that reached us
        self.created_count = 0
        self._remaining_failures = fail_times
        self._fail_mode = fail_mode  # "500" or "timeout"
        self._fail_delay = fail_delay
        self._counter = 0
        self._lock = threading.Lock()
        self._server = None
        self._thread = None

    @property
    def base_url(self):
        host, port = self._server.server_address
        return f"http://127.0.0.1:{port}"

    def start(self):
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                outer._handle(self)

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def stop(self):
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.stop()

    def _handle(self, h):
        with self._lock:
            self.requests_seen += 1
            inject = self._remaining_failures > 0
            if inject:
                self._remaining_failures -= 1
        if inject:
            if self._fail_mode == "timeout":
                time.sleep(self._fail_delay)
                # fall through and answer; the client should have timed out
            else:
                h.send_response(500)
                h.end_headers()
                h.wfile.write(b'{"detail":"injected failure"}')
                return

        length = int(h.headers.get("Content-Length", 0))
        body = h.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(body)
        except ValueError:
            payload = {}

        store_id = h.headers.get("Store-Id")
        idem = h.headers.get("Idempotency-Key")

        if not payload.get("coffeeType") or not payload.get("price"):
            h.send_response(400)
            h.send_header("Content-Type", "application/problem+json")
            h.end_headers()
            h.wfile.write(b'{"detail":"price must be greater than zero"}')
            return

        key = (store_id, idem)
        with self._lock:
            if key in self.payments:
                payment_id, status = self.payments[key], 200
            else:
                self._counter += 1
                payment_id = f"pay-{self._counter}"
                self.payments[key] = payment_id
                self.created_count += 1
                status = 201
        h.send_response(status)
        h.send_header("Content-Type", "application/json")
        h.end_headers()
        h.wfile.write(json.dumps({"paymentId": payment_id, "storeId": store_id}).encode())
```

- [ ] **Step 2: Smoke-test the fake server**

Run: `python3 -c "from tests._fake_server import FakeCentral; s=FakeCentral().start(); print(s.base_url); s.stop()"`
Expected: prints a `http://127.0.0.1:<port>` URL with no error

- [ ] **Step 3: Commit**

```bash
git add tools/coffee-payments-sync/tests/_fake_server.py
git commit -m "test(sync): in-process fake Central System with fault injection"
```

---

## Task 5: Reliable HTTP client

POSTs one row with a stable idempotency key, retrying retryable failures with
exponential backoff + jitter; never retries 4xx.

**Files:**
- Create: `tools/coffee-payments-sync/coffee_sync/client.py`
- Test: `tools/coffee-payments-sync/tests/test_client.py`

- [ ] **Step 1: Write the failing tests**

`tools/coffee-payments-sync/tests/test_client.py`:
```python
import unittest

from coffee_sync.client import PaymentClient, SendResult
from coffee_sync.parser import PaymentRow
from tests._fake_server import FakeCentral


def row(row_number=2, idem="key-1"):
    return PaymentRow(
        store_id="STORE1", coffee_type="LATTE", price="3.50",
        currency="EUR", loyalty_card_id="card-1",
        row_number=row_number, idempotency_key=idem,
    )


# Zero backoff base keeps tests fast.
def client(base_url, **kw):
    return PaymentClient(base_url=base_url, timeout=1.0, max_retries=5,
                         backoff_base=0.0, backoff_cap=0.0, **kw)


class PaymentClientTest(unittest.TestCase):
    def test_new_payment_returns_created(self):
        with FakeCentral() as srv:
            res = client(srv.base_url).send(row())
            self.assertEqual(res.outcome, "created")
            self.assertEqual(res.payment_id, "pay-1")
            self.assertEqual(srv.created_count, 1)

    def test_same_key_replays_as_200(self):
        with FakeCentral() as srv:
            c = client(srv.base_url)
            first = c.send(row(idem="dup"))
            second = c.send(row(idem="dup"))
            self.assertEqual(first.outcome, "created")
            self.assertEqual(second.outcome, "replayed")
            self.assertEqual(second.payment_id, first.payment_id)
            self.assertEqual(srv.created_count, 1)

    def test_retries_500_then_succeeds(self):
        with FakeCentral(fail_times=2, fail_mode="500") as srv:
            res = client(srv.base_url).send(row())
            self.assertEqual(res.outcome, "created")
            self.assertEqual(srv.requests_seen, 3)  # 2 failures + 1 success

    def test_retry_after_lost_response_does_not_duplicate(self):
        # Server succeeds but first response is "lost" via a timeout; the stable
        # idempotency key means the retry replays instead of creating a second.
        with FakeCentral(fail_times=1, fail_mode="timeout", fail_delay=2.0) as srv:
            res = client(srv.base_url).send(row(idem="lost"))
            self.assertIn(res.outcome, ("created", "replayed"))
            self.assertEqual(srv.created_count, 1)

    def test_400_is_not_retried_and_reports_detail(self):
        with FakeCentral() as srv:
            bad = PaymentRow(
                store_id="STORE1", coffee_type="LATTE", price="",
                currency="EUR", loyalty_card_id="c",
                row_number=2, idempotency_key="bad",
            )
            res = client(srv.base_url).send(bad)
            self.assertEqual(res.outcome, "failed")
            self.assertIn("price", res.detail)
            self.assertEqual(srv.requests_seen, 1)  # not retried

    def test_exhausted_retries_returns_failed(self):
        with FakeCentral(fail_times=99, fail_mode="500") as srv:
            res = client(srv.base_url).send(row())
            self.assertEqual(res.outcome, "failed")
            self.assertEqual(srv.requests_seen, 5)  # max_retries attempts


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_client -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'coffee_sync.client'`

- [ ] **Step 3: Write the client implementation**

`tools/coffee-payments-sync/coffee_sync/client.py`:
```python
"""HTTP client that registers one payment reliably.

Reliability model:
- A stable Idempotency-Key header (from parser.idempotency_key) is sent on every
  attempt, so a retry after a lost response replays (200) instead of creating a
  duplicate.
- Retryable failures (connection errors, timeouts, 429, 5xx) are retried with
  exponential backoff + jitter, bounded by max_retries.
- 4xx (other than 429) is permanent: never retried; the server's detail message
  is captured and the row is reported as failed.
"""

from __future__ import annotations

import json
import random
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

from .parser import idempotency_key

PAYMENTS_PATH = "/api/v1/payments"


@dataclass(frozen=True)
class SendResult:
    outcome: str        # "created" | "replayed" | "failed"
    idempotency_key: str
    payment_id: str = ""
    detail: str = ""    # failure reason (server message or last error)


class PaymentClient:
    def __init__(self, base_url, timeout=10.0, max_retries=5,
                 backoff_base=0.5, backoff_cap=8.0, sleep=time.sleep,
                 rand=random.random):
        self.url = base_url.rstrip("/") + PAYMENTS_PATH
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.backoff_cap = backoff_cap
        self._sleep = sleep
        self._rand = rand

    def send(self, row):
        key = idempotency_key(row)
        body = json.dumps({
            "coffeeType": row.coffee_type,
            "price": row.price,
            "currency": row.currency,
            "loyaltyCardId": row.loyalty_card_id,
        }).encode("utf-8")

        last_detail = ""
        for attempt in range(self.max_retries):
            if attempt > 0:
                self._backoff(attempt)
            outcome, payment_id, detail, retryable = self._attempt(body, row.store_id, key)
            if outcome != "failed":
                return SendResult(outcome, key, payment_id)
            last_detail = detail
            if not retryable:
                return SendResult("failed", key, detail=detail)
        return SendResult("failed", key, detail=last_detail or "retries exhausted")

    def _attempt(self, body, store_id, key):
        """Returns (outcome, payment_id, detail, retryable)."""
        request = urllib.request.Request(self.url, data=body, method="POST")
        request.add_header("Content-Type", "application/json")
        request.add_header("Store-Id", store_id)
        request.add_header("Idempotency-Key", key)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as resp:
                status = resp.status
                payload = self._read_json(resp.read())
                payment_id = payload.get("paymentId", "")
                return ("created" if status == 201 else "replayed"), payment_id, "", False
        except urllib.error.HTTPError as err:
            detail = self._error_detail(err)
            retryable = err.code == 429 or err.code >= 500
            return "failed", "", detail, retryable
        except (urllib.error.URLError, TimeoutError, OSError) as err:
            return "failed", "", f"network error: {err}", True

    def _backoff(self, attempt):
        delay = min(self.backoff_cap, self.backoff_base * (2 ** (attempt - 1)))
        self._sleep(delay + self._rand() * self.backoff_base)

    @staticmethod
    def _read_json(raw):
        try:
            return json.loads(raw or b"{}")
        except ValueError:
            return {}

    @staticmethod
    def _error_detail(err):
        try:
            payload = json.loads(err.read() or b"{}")
            return payload.get("detail") or f"HTTP {err.code}"
        except ValueError:
            return f"HTTP {err.code}"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_client -v`
Expected: PASS (all six tests)

- [ ] **Step 5: Commit**

```bash
git add tools/coffee-payments-sync/coffee_sync/client.py tools/coffee-payments-sync/tests/test_client.py
git commit -m "feat(sync): reliable HTTP client with retry, backoff and idempotency"
```

---

## Task 6: CLI orchestration + reporting

Wires parser, client, and ledger together; prints a summary; sets exit code.

**Files:**
- Create: `tools/coffee-payments-sync/coffee_sync/__main__.py`
- Test: `tools/coffee-payments-sync/tests/test_end_to_end.py`

- [ ] **Step 1: Write the failing end-to-end tests**

`tools/coffee-payments-sync/tests/test_end_to_end.py`:
```python
import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout

from coffee_sync.__main__ import run
from coffee_sync.ledger import Ledger
from tests._fake_server import FakeCentral

CSV = (
    "coffee_type,price,currency,loyalty_card_id\n"
    "LATTE,3.50,EUR,card-1\n"
    "ESPRESSO,2.00,EUR,card-2\n"
    "TEA,9.99,EUR,card-3\n"        # invalid coffee_type -> local failure
)


class EndToEndTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.csv_path = os.path.join(self.dir, "payments.csv")
        with open(self.csv_path, "w", encoding="utf-8") as fh:
            fh.write(CSV)
        self.ledger_path = os.path.join(self.dir, "run.ledger.jsonl")

    def _run(self, base_url, **over):
        args = dict(store_id="STORE1", csv_path=self.csv_path,
                    base_url=base_url, ledger_path=self.ledger_path,
                    max_retries=5, timeout=1.0, dry_run=False)
        args.update(over)
        out = io.StringIO()
        with redirect_stdout(out):
            code = run(**args)
        return code, out.getvalue()

    def test_full_run_sends_valid_skips_invalid(self):
        with FakeCentral() as srv:
            code, out = self._run(srv.base_url)
            self.assertEqual(srv.created_count, 2)      # two valid rows
            self.assertEqual(code, 1)                   # one failed row
            self.assertIn("2 created", out)
            self.assertIn("1 failed", out)

    def test_rerun_skips_already_confirmed(self):
        with FakeCentral() as srv:
            self._run(srv.base_url)
            self.assertEqual(srv.created_count, 2)
            # second run: ledger already has the two confirmed keys
            code, out = self._run(srv.base_url)
            self.assertEqual(srv.created_count, 2)       # nothing new created
            self.assertIn("2 skipped", out)

    def test_ledger_records_confirmed_rows(self):
        with FakeCentral() as srv:
            self._run(srv.base_url)
        self.assertEqual(len(Ledger(self.ledger_path).confirmed_keys()), 2)

    def test_dry_run_sends_nothing(self):
        with FakeCentral() as srv:
            code, out = self._run(srv.base_url, dry_run=True)
            self.assertEqual(srv.requests_seen, 0)
            self.assertFalse(os.path.exists(self.ledger_path))
            self.assertIn("dry-run", out.lower())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_end_to_end -v`
Expected: FAIL — `ImportError: cannot import name 'run' from 'coffee_sync.__main__'`

- [ ] **Step 3: Write the CLI implementation**

`tools/coffee-payments-sync/coffee_sync/__main__.py`:
```python
"""CLI entry point: read the CSV, send each payment reliably, resume from the
ledger, and print a summary. Exit code is non-zero if any row failed."""

from __future__ import annotations

import argparse
import sys

from .client import PaymentClient
from .ledger import Ledger
from .parser import idempotency_key, parse_rows


def run(store_id, csv_path, base_url, ledger_path, max_retries, timeout, dry_run):
    with open(csv_path, "r", encoding="utf-8", newline="") as fh:
        rows, errors = parse_rows(fh, default_store_id=store_id)

    counts = {"created": 0, "replayed": 0, "skipped": 0, "failed": 0}
    failures = [(e.row_number, e.message) for e in errors]
    counts["failed"] += len(errors)

    if dry_run:
        print(f"[dry-run] {len(rows)} valid row(s) would be sent; "
              f"{len(errors)} invalid row(s) would be skipped.")
        _print_failures(failures)
        return 1 if failures else 0

    ledger = Ledger(ledger_path)
    confirmed = ledger.confirmed_keys()
    client = PaymentClient(base_url=base_url, timeout=timeout, max_retries=max_retries)

    for row in rows:
        if idempotency_key(row) in confirmed:
            counts["skipped"] += 1
            continue
        result = client.send(row)
        counts[result.outcome] += 1
        if result.outcome in ("created", "replayed"):
            ledger.record(result.idempotency_key, result.payment_id, result.outcome)
        else:
            failures.append((row.row_number, result.detail))

    _print_summary(rows, errors, counts, failures)
    return 0 if counts["failed"] == 0 else 1


def _print_summary(rows, errors, counts, failures):
    total = len(rows) + len(errors)
    print(f"Processed {total} rows: "
          f"{counts['created']} created, {counts['replayed']} replayed, "
          f"{counts['skipped']} skipped, {counts['failed']} failed")
    _print_failures(failures)


def _print_failures(failures):
    if failures:
        print("Failures:")
        for row_number, message in sorted(failures):
            print(f"  row {row_number}: {message}")


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="coffee_sync",
        description="Reliably propagate a CSV of coffee sales to the StarHarbour Central System.",
    )
    parser.add_argument("csv_path", help="path to the day's payments CSV")
    parser.add_argument("--store-id", required=True, help="default Store-Id for rows without one")
    parser.add_argument("--base-url", default="http://localhost:8080",
                        help="Central System base URL (use http://localhost:9091 for Toxiproxy)")
    parser.add_argument("--ledger", dest="ledger_path", default=None,
                        help="resume ledger path (default: <csv>.ledger.jsonl)")
    parser.add_argument("--max-retries", type=int, default=5)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    ledger_path = args.ledger_path or (args.csv_path + ".ledger.jsonl")
    return run(
        store_id=args.store_id,
        csv_path=args.csv_path,
        base_url=args.base_url,
        ledger_path=ledger_path,
        max_retries=args.max_retries,
        timeout=args.timeout,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_end_to_end -v`
Expected: PASS

- [ ] **Step 5: Run the full suite**

Run: `python3 -m unittest discover -s tests -v`
Expected: PASS (all tests across parser, ledger, client, end-to-end)

- [ ] **Step 6: Commit**

```bash
git add tools/coffee-payments-sync/coffee_sync/__main__.py tools/coffee-payments-sync/tests/test_end_to_end.py
git commit -m "feat(sync): CLI orchestration, reporting and resume"
```

---

## Task 7: Sample CSV + README

**Files:**
- Create: `tools/coffee-payments-sync/sample_payments.csv`
- Create: `tools/coffee-payments-sync/README.md`

- [ ] **Step 1: Write the sample CSV**

`tools/coffee-payments-sync/sample_payments.csv`:
```csv
coffee_type,price,currency,loyalty_card_id
LATTE,3.50,EUR,card-1001
ESPRESSO,2.00,EUR,card-1002
DOUBLE_ESPRESSO,2.80,EUR,card-1003
CAPPUCCINO,3.20,EUR,card-1001
COLD_BREW,4.10,EUR,card-1004
```

- [ ] **Step 2: Write the README**

`tools/coffee-payments-sync/README.md`:
```markdown
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
```

- [ ] **Step 3: Verify the CLI runs against the sample (dry-run, no server needed)**

Run: `python3 -m coffee_sync --store-id STORE123 --dry-run sample_payments.csv`
Expected: prints `[dry-run] 5 valid row(s) would be sent; 0 invalid row(s) would be skipped.` and exits 0

- [ ] **Step 4: Commit**

```bash
git add tools/coffee-payments-sync/sample_payments.csv tools/coffee-payments-sync/README.md
git commit -m "docs(sync): sample CSV and README"
```

---

## Task 8: Top-level README pointer + open PR

**Files:**
- Modify: `README.md` (repo root — add a short pointer to the tool)

- [ ] **Step 1: Append a pointer to the root README**

Add this section near the end of the root `README.md` (keep existing content):
```markdown
## Client tools

- [`tools/coffee-payments-sync/`](tools/coffee-payments-sync/) — a zero-dependency
  Python CLI that propagates a CSV of a day's coffee sales to the payments API,
  reliably (idempotency keys + retry/backoff + resume ledger) even under
  Toxiproxy fault injection. See its README and the
  [design doc](docs/superpowers/specs/2026-06-12-coffee-payments-sync-design.md).
```

- [ ] **Step 2: Run the full test suite one more time**

Run (from `tools/coffee-payments-sync/`): `python3 -m unittest discover -s tests -v`
Expected: PASS (all tests)

- [ ] **Step 3: Confirm the server's own tests still pass (we changed only docs + new dir)**

Run (from repo root): `./gradlew test`
Expected: BUILD SUCCESSFUL (no Java source was modified)

- [ ] **Step 4: Commit and push**

```bash
git add README.md
git commit -m "docs: link coffee-payments-sync client tool from root README"
git push -u origin feature/csv-payments-sync
```

- [ ] **Step 5: Open the PR**

```bash
gh pr create --repo igor-sakhankov/harbour-cloud-26 \
  --head mkhlndrv:feature/csv-payments-sync \
  --title "Add coffee-payments-sync: reliable CSV payment uploader" \
  --body "Implements an end-of-day CSV uploader that propagates coffee payments to the Central System reliably under Toxiproxy fault injection — stable per-row idempotency keys, retry with exponential backoff + jitter, no-retry on 400, and an append-only resume ledger. Zero runtime dependencies (Python 3 stdlib). Includes unit + end-to-end tests using an in-process fake Central System. See tools/coffee-payments-sync/README.md and the design doc under docs/superpowers/specs/."
```

---

## Self-Review

**Spec coverage:**
- API contract & validation → Task 2 ✓
- Stable idempotency key derivation → Task 2 ✓
- Retry/backoff, no-retry-on-400, lost-response safety → Task 5 ✓
- Resume ledger → Task 3, used in Task 6 ✓
- CLI flags, reporting, exit code, dry-run → Task 6 ✓
- Sample CSV + README + design-doc link → Tasks 7, 8 ✓
- Tests (parser cases, idempotency, client fault injection, e2e resume) → Tasks 2–6 ✓
- Deliverable PR from the fork → Task 8 ✓

**Placeholder scan:** none — every code/test step contains full content.

**Type consistency:** `PaymentRow`/`RowError` fields, `parse_rows()`, `idempotency_key()`, `Ledger.confirmed_keys()/record()`, `PaymentClient.send()` and `SendResult.outcome ∈ {created, replayed, failed}` are used identically across Tasks 2–6. `run(...)` keyword args match between Task 6's implementation and the end-to-end test.
