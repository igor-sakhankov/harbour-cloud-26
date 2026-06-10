#!/usr/bin/env python3
"""
upload_payments.py — Upload offline coffee payments from a CSV file to the
StarHarbour Payments API with idempotent, retry-safe delivery.

Usage:
    python upload_payments.py payments.csv
    python upload_payments.py payments.csv --url http://localhost:9091/api/v1/payments

CSV columns (header row required):
    store_id        — required
    transaction_id  — optional; auto-generated from row content if absent
    coffee_type     — required; must match API enum (e.g. LATTE, ESPRESSO)
    price           — required; positive decimal, max 2 decimal places
    currency        — required; 3-letter ISO-4217 code (e.g. EUR)
    loyalty_card_id — optional; leave blank if none
"""

import argparse
import csv
import hashlib
import sys
import time
from pathlib import Path

import requests
from requests.exceptions import ConnectionError, RequestException, Timeout

DEFAULT_URL = "http://localhost:8080/api/v1/payments"
MAX_RETRIES = 5
INITIAL_BACKOFF_S = 1.0
MAX_BACKOFF_S = 30.0

VALID_COFFEE_TYPES = {
    "ESPRESSO", "DOUBLE_ESPRESSO", "AMERICANO", "LATTE",
    "CAPPUCCINO", "FLAT_WHITE", "MOCHA", "CORTADO", "MACCHIATO", "COLD_BREW",
}


def deterministic_idempotency_key(store_id: str, coffee_type: str, price: str,
                                   currency: str, loyalty_card_id: str, row_index: int) -> str:
    """MD5 of all stable row fields so the same file always produces the same key."""
    raw = f"{store_id}:{coffee_type}:{price}:{currency}:{loyalty_card_id}:{row_index}"
    return hashlib.md5(raw.encode()).hexdigest()


def send_with_retry(url: str, store_id: str, idempotency_key: str, payload: dict) -> requests.Response:
    headers = {
        "Content-Type": "application/json",
        "Store-Id": store_id,
        "Idempotency-Key": idempotency_key,
    }
    backoff = INITIAL_BACKOFF_S

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=10)
            if resp.status_code < 500:
                return resp  # success or client error — no retry
            msg = f"HTTP {resp.status_code}"
        except (ConnectionError, Timeout) as exc:
            msg = f"{type(exc).__name__}: {exc}"
        except RequestException as exc:
            msg = f"RequestException: {exc}"

        if attempt == MAX_RETRIES:
            break
        print(f"    [attempt {attempt}/{MAX_RETRIES}] {msg} — retrying in {backoff:.1f}s...")
        time.sleep(backoff)
        backoff = min(backoff * 2, MAX_BACKOFF_S)

    raise RuntimeError(f"All {MAX_RETRIES} attempts failed. Last error: {msg}")


def process_row(row: dict, row_index: int, url: str) -> bool:
    store_id       = row.get("store_id", "").strip()
    transaction_id = row.get("transaction_id", "").strip()
    coffee_type    = row.get("coffee_type", "").strip().upper()
    price_str      = row.get("price", "").strip()
    currency       = row.get("currency", "").strip().upper()
    loyalty_card_id = row.get("loyalty_card_id", "").strip()

    # --- local validation (fail fast, no HTTP call) ---
    errors = []
    if not store_id:
        errors.append("store_id is missing")
    if not coffee_type:
        errors.append("coffee_type is missing")
    elif coffee_type not in VALID_COFFEE_TYPES:
        errors.append(
            f"coffee_type '{coffee_type}' is not valid "
            f"(valid: {', '.join(sorted(VALID_COFFEE_TYPES))})"
        )
    if not price_str:
        errors.append("price is missing")
    else:
        try:
            price_val = round(float(price_str), 2)
            if price_val <= 0:
                errors.append("price must be greater than zero")
        except ValueError:
            errors.append(f"price '{price_str}' is not a number")
            price_val = None
    if not currency:
        errors.append("currency is missing")

    if errors:
        print(f"  [SKIP   ] Row {row_index}: {'; '.join(errors)}")
        return False

    if not transaction_id:
        transaction_id = deterministic_idempotency_key(
            store_id, coffee_type, price_str, currency, loyalty_card_id, row_index
        )
        print(f"  [INFO   ] Row {row_index}: no transaction_id — generated key: {transaction_id}")

    payload = {
        "coffeeType": coffee_type,
        "price": price_val,
        "currency": currency,
        "loyaltyCardId": loyalty_card_id,
    }

    try:
        resp = send_with_retry(url, store_id, transaction_id, payload)
    except RuntimeError as exc:
        print(f"  [FAIL   ] Row {row_index} store={store_id} key={transaction_id}: {exc}")
        return False

    if resp.status_code == 201:
        payment_id = resp.json().get("paymentId", "?")
        print(
            f"  [CREATED] Row {row_index}: paymentId={payment_id} "
            f"store={store_id} {coffee_type} {price_str} {currency}"
        )
        return True

    if resp.status_code == 200:
        payment_id = resp.json().get("paymentId", "?")
        print(
            f"  [EXISTS ] Row {row_index}: paymentId={payment_id} "
            f"store={store_id} key={transaction_id} — idempotent replay, no duplicate created"
        )
        return True

    if resp.status_code == 400:
        try:
            problem = resp.json()
            detail = problem.get("detail", resp.text)
            field_errors = problem.get("errors", [])
        except Exception:
            detail = resp.text
            field_errors = []
        summary = f"detail='{detail}'"
        if field_errors:
            summary += f" errors={field_errors}"
        print(f"  [INVALID] Row {row_index} store={store_id}: 400 Bad Request — {summary}")
        return False

    print(f"  [FAIL   ] Row {row_index}: unexpected status {resp.status_code}: {resp.text[:200]}")
    return False


def main():
    parser = argparse.ArgumentParser(
        description="Upload offline CSV payments to the StarHarbour Payments API."
    )
    parser.add_argument("csv_file", help="Path to the payments CSV file")
    parser.add_argument(
        "--url",
        default=DEFAULT_URL,
        help=f"API base URL (default: {DEFAULT_URL})",
    )
    args = parser.parse_args()

    csv_path = Path(args.csv_file)
    if not csv_path.exists():
        print(f"Error: file not found: {csv_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Uploading '{csv_path}' → {args.url}\n")

    successes = 0
    failures = 0

    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row_index, row in enumerate(reader, start=1):
            if process_row(row, row_index, args.url):
                successes += 1
            else:
                failures += 1

    total = successes + failures
    print(f"\n{'=' * 52}")
    print(f"Summary: {successes}/{total} processed successfully, {failures} failed.")
    sys.exit(0 if failures == 0 else 1)


if __name__ == "__main__":
    main()
