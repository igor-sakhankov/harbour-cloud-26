"""
Reliable CSV -> StarHarbour Payments importer (CLI).

Reads an end-of-day coffee-payment ledger from a CSV file and pushes every row
into the Payments API, reliably:

  * stable per-row Idempotency-Key (the order_id) so retries never duplicate;
  * exponential backoff + jitter on transient failures (timeout / reset / 5xx);
  * 400 (bad data) is non-retryable -- reported and skipped;
  * optional read-back verification that the server holds each payment once.

CSV columns: order_id,store_id,coffee_type,price,currency,loyalty_card_id

Usage:
    python import_payments.py payments.csv
    python import_payments.py payments.csv --base-url http://localhost:9091 --verify
    python import_payments.py payments.csv --charts out.png
"""
import argparse
import csv
import random
import sys
import time
from collections import Counter

import requests

# --- Defaults (overridable via CLI) -----------------------------------------
DEFAULT_BASE_URL = "http://localhost:9091"   # Toxiproxy proxy -> app:8080
MAX_RETRIES = 5
BASE_BACKOFF = 0.5          # seconds
MAX_BACKOFF = 8.0
CONNECT_TIMEOUT = 3.05
READ_TIMEOUT = 6.0
RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504}

REQUIRED_COLUMNS = {
    "order_id", "store_id", "coffee_type", "price", "currency", "loyalty_card_id",
}


def load_csv(path):
    with open(path, newline="") as fh:
        reader = csv.DictReader(fh)
        missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
        if missing:
            raise SystemExit(f"CSV is missing required columns: {sorted(missing)}")
        return list(reader)


def is_retryable_status(code):
    return code in RETRYABLE_STATUS


def send_payment(row, base_url, max_retries=MAX_RETRIES):
    """POST one CSV row, retrying only transient failures. Returns a result dict."""
    idem_key = str(row["order_id"]).strip()
    headers = {
        "Store-Id": str(row["store_id"]).strip(),
        "Idempotency-Key": idem_key,
        "Content-Type": "application/json",
    }
    try:
        price = float(row["price"])
    except (TypeError, ValueError):
        price = row["price"]   # let the server reject it with a 400
    body = {
        "coffeeType": row["coffee_type"],
        "price": price,
        "currency": row["currency"],
        "loyaltyCardId": row["loyalty_card_id"],
    }

    attempts = 0
    started = time.time()
    last_error = None

    while attempts <= max_retries:
        attempts += 1
        try:
            resp = requests.post(
                f"{base_url}/api/v1/payments",
                headers=headers, json=body,
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
            )
            if resp.status_code in (200, 201):
                payment = resp.json()
                return {
                    "order_id": idem_key, "store_id": headers["Store-Id"],
                    "ok": True, "http": resp.status_code,
                    "created": resp.status_code == 201,
                    "replayed": resp.status_code == 200,
                    "payment_id": payment.get("paymentId"),
                    "attempts": attempts,
                    "latency_s": round(time.time() - started, 3),
                    "error": None,
                }
            if not is_retryable_status(resp.status_code):
                # e.g. 400 bad data -- retrying will never help.
                return {
                    "order_id": idem_key, "store_id": headers["Store-Id"],
                    "ok": False, "http": resp.status_code,
                    "created": False, "replayed": False, "payment_id": None,
                    "attempts": attempts,
                    "latency_s": round(time.time() - started, 3),
                    "error": resp.text[:200],
                }
            last_error = f"HTTP {resp.status_code}"
        except (requests.ConnectionError, requests.Timeout) as exc:
            last_error = type(exc).__name__

        if attempts <= max_retries:
            backoff = min(MAX_BACKOFF, BASE_BACKOFF * (2 ** (attempts - 1)))
            backoff *= 0.5 + random.random()      # jitter to avoid retry storms
            time.sleep(backoff)

    return {
        "order_id": idem_key, "store_id": headers["Store-Id"],
        "ok": False, "http": None, "created": False, "replayed": False,
        "payment_id": None, "attempts": attempts,
        "latency_s": round(time.time() - started, 3),
        "error": f"exhausted retries ({last_error})",
    }


def import_ledger(rows, base_url, verbose=True):
    results = []
    for i, row in enumerate(rows, 1):
        res = send_payment(row, base_url)
        results.append(res)
        if verbose:
            if res["ok"]:
                tag = "created" if res["created"] else "replayed"
                print(f"[{i:>3}/{len(rows)}] {res['order_id']:<10} "
                      f"{res['http']} {tag} (attempts={res['attempts']})")
            else:
                print(f"[{i:>3}/{len(rows)}] {res['order_id']:<10} "
                      f"FAILED http={res['http']} attempts={res['attempts']} "
                      f"-- {res['error']}", file=sys.stderr)
    return results


def verify_exactly_once(rows, base_url):
    """Read each store's ledger back and check for duplicate paymentIds."""
    store_ids = sorted({r["store_id"].strip() for r in rows})
    seen = []
    for store_id in store_ids:
        resp = requests.get(f"{base_url}/api/v1/payments",
                            params={"storeId": store_id}, timeout=(3, 10))
        resp.raise_for_status()
        seen.extend(p["paymentId"] for p in resp.json())
    dupes = [pid for pid, n in Counter(seen).items() if n > 1]
    return len(seen), dupes


def print_summary(results):
    delivered = sum(r["ok"] for r in results)
    created = sum(r["created"] for r in results)
    replayed = sum(r["replayed"] for r in results)
    failed = sum(not r["ok"] for r in results)
    attempts = sum(r["attempts"] for r in results)
    print("\n=== Summary ===")
    print(f"rows:          {len(results)}")
    print(f"delivered:     {delivered}  (created={created}, replayed={replayed})")
    print(f"failed:        {failed}")
    print(f"HTTP attempts: {attempts}  (retries used: {attempts - len(results)})")
    if failed:
        print("failed rows:")
        for r in results:
            if not r["ok"]:
                print(f"  - {r['order_id']}: http={r['http']} {r['error']}")


def save_charts(results, rows, path):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not installed -- skipping charts.", file=sys.stderr)
        return

    by_order = {r["order_id"]: r for r in rows}
    coffee = Counter(by_order[r["order_id"]]["coffee_type"]
                     for r in results if r["ok"] and r["order_id"] in by_order)
    attempts = Counter(r["attempts"] for r in results)

    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    if coffee:
        axes[0].bar(list(coffee), list(coffee.values()), color="#6f4e37")
    axes[0].set_title("Cups sold by coffee type")
    axes[0].tick_params(axis="x", rotation=45)
    xs = sorted(attempts)
    axes[1].bar([str(x) for x in xs], [attempts[x] for x in xs], color="#e76f51")
    axes[1].set_title("HTTP attempts per payment")
    axes[1].set_xlabel("attempts")
    fig.tight_layout()
    fig.savefig(path)
    print(f"charts written to {path}")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Reliably import a coffee-payment CSV into the StarHarbour Payments API.")
    parser.add_argument("csv_path", help="path to the payments CSV file")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL,
                        help=f"Payments API base URL (default: {DEFAULT_BASE_URL}, the Toxiproxy port)")
    parser.add_argument("--verify", action="store_true",
                        help="read the ledger back and assert no duplicate payments")
    parser.add_argument("--charts", metavar="PNG",
                        help="write summary charts to this PNG file")
    parser.add_argument("--quiet", action="store_true", help="suppress per-row logging")
    args = parser.parse_args(argv)

    rows = load_csv(args.csv_path)
    print(f"Loaded {len(rows)} rows from {args.csv_path}; sending to {args.base_url}")

    results = import_ledger(rows, args.base_url, verbose=not args.quiet)
    print_summary(results)

    exit_code = 0
    if args.verify:
        total, dupes = verify_exactly_once(rows, args.base_url)
        print(f"\n=== Verification ===")
        print(f"server payments: {total}; duplicates: {len(dupes)}")
        if dupes:
            print(f"DUPLICATE paymentIds: {dupes}", file=sys.stderr)
            exit_code = 1
        else:
            print("OK: every delivered payment is recorded exactly once.")

    if args.charts:
        save_charts(results, rows, args.charts)

    # Non-zero exit if any row failed for a non-validation reason (network exhaustion).
    if any(not r["ok"] and r["http"] is None for r in results):
        exit_code = 1
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
