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
