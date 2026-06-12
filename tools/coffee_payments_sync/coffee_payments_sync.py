#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import http.client
import json
import os
import random
import re
import socket
import sys
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable


API_PATH = "/api/v1/payments"
CSV_NAMESPACE = uuid.UUID("25e07d45-1e31-4fe2-8844-0dc23aa97937")

COFFEE_TYPES = {
    "ESPRESSO",
    "DOUBLE_ESPRESSO",
    "AMERICANO",
    "LATTE",
    "CAPPUCCINO",
    "FLAT_WHITE",
    "MOCHA",
    "CORTADO",
    "MACCHIATO",
    "COLD_BREW",
}

FIELD_ALIASES = {
    "store_id": ("store_id", "storeid", "store", "store-id", "Store-Id"),
    "coffee_type": ("coffee_type", "coffeetype", "coffee", "drink", "item"),
    "price": ("price", "amount"),
    "currency": ("currency", "ccy"),
    "loyalty_card_id": (
        "loyalty_card_id",
        "loyaltycardid",
        "loyalty_card",
        "loyalty",
        "card_id",
    ),
    "idempotency_key": (
        "idempotency_key",
        "idempotencykey",
        "Idempotency-Key",
        "idempotency",
    ),
}

UNIQUE_REFERENCE_ALIASES = (
    "transaction_id",
    "transactionid",
    "payment_id",
    "paymentid",
    "order_id",
    "orderid",
    "notebook_entry_id",
    "notebookentryid",
    "reference",
    "ref",
)


class CsvValidationError(Exception):
    """Raised when the input CSV cannot be safely sent."""


class TransientPaymentError(Exception):
    """Raised for a failure that may succeed when retried."""


class PermanentPaymentError(Exception):
    """Raised for a failure that should not be retried as-is."""


@dataclass(frozen=True)
class PaymentRow:
    line_number: int
    store_id: str
    coffee_type: str
    price: Decimal
    currency: str
    loyalty_card_id: str
    idempotency_key: str


@dataclass(frozen=True)
class PaymentResult:
    http_status: int
    body: dict[str, Any]


@dataclass
class SyncSummary:
    total: int = 0
    sent: int = 0
    skipped: int = 0
    failed: int = 0
    retried: int = 0
    dry_run: bool = False
    failures: list[str] = field(default_factory=list)


class SyncJournal:
    def __init__(self, path: Path):
        self.path = path
        self.data = self._load()

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"version": 1, "rows": {}}

        try:
            with self.path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        except json.JSONDecodeError as exc:
            raise CsvValidationError(f"State file is not valid JSON: {self.path}") from exc

        if not isinstance(data, dict) or not isinstance(data.get("rows"), dict):
            raise CsvValidationError(f"State file has an unexpected format: {self.path}")

        data.setdefault("version", 1)
        return data

    def is_sent(self, row: PaymentRow) -> bool:
        record = self.data["rows"].get(self._row_key(row))
        return bool(record and record.get("status") == "sent")

    def mark_sent(self, row: PaymentRow, result: PaymentResult, attempts: int) -> None:
        self.data["rows"][self._row_key(row)] = {
            "status": "sent",
            "storeId": row.store_id,
            "idempotencyKey": row.idempotency_key,
            "lineNumber": row.line_number,
            "paymentId": result.body.get("paymentId"),
            "httpStatus": result.http_status,
            "attempts": attempts,
            "updatedAt": utc_now(),
        }
        self.save()

    def mark_failed(self, row: PaymentRow, message: str, attempts: int) -> None:
        self.data["rows"][self._row_key(row)] = {
            "status": "failed",
            "storeId": row.store_id,
            "idempotencyKey": row.idempotency_key,
            "lineNumber": row.line_number,
            "error": message,
            "attempts": attempts,
            "updatedAt": utc_now(),
        }
        self.save()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(self.data, handle, indent=2, sort_keys=True)
            handle.write("\n")
        tmp_path.replace(self.path)

    @staticmethod
    def _row_key(row: PaymentRow) -> str:
        material = f"{row.store_id}\n{row.idempotency_key}".encode("utf-8")
        return hashlib.sha256(material).hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def default_state_file(csv_path: Path) -> Path:
    return csv_path.with_suffix(csv_path.suffix + ".sync-state.json")


def parse_csv(csv_path: Path, source_id: str | None = None) -> list[PaymentRow]:
    source = source_id or csv_path.name
    rows: list[PaymentRow] = []

    try:
        with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames:
                raise CsvValidationError("CSV file is empty or missing a header row")

            for line_number, raw_row in enumerate(reader, start=2):
                if is_blank_row(raw_row):
                    continue
                rows.append(parse_row(raw_row, line_number, source))
    except FileNotFoundError as exc:
        raise CsvValidationError(f"CSV file not found: {csv_path}") from exc

    if not rows:
        raise CsvValidationError("CSV file contains no payment rows")

    return rows


def parse_row(raw_row: dict[str, str | None], line_number: int, source_id: str) -> PaymentRow:
    normalized = normalize_row(raw_row)

    store_id = required_value(normalized, "store_id", line_number)
    coffee_type = normalize_coffee_type(required_value(normalized, "coffee_type", line_number), line_number)
    price = parse_price(required_value(normalized, "price", line_number), line_number)
    currency = normalize_currency(required_value(normalized, "currency", line_number), line_number)
    loyalty_card_id = required_value(normalized, "loyalty_card_id", line_number)

    idempotency_key = explicit_idempotency_key(normalized)
    if not idempotency_key:
        idempotency_key = derive_idempotency_key(
            source_id=source_id,
            line_number=line_number,
            store_id=store_id,
            coffee_type=coffee_type,
            price=price,
            currency=currency,
            loyalty_card_id=loyalty_card_id,
            normalized_row=normalized,
        )

    return PaymentRow(
        line_number=line_number,
        store_id=store_id,
        coffee_type=coffee_type,
        price=price,
        currency=currency,
        loyalty_card_id=loyalty_card_id,
        idempotency_key=idempotency_key,
    )


def normalize_row(raw_row: dict[str, str | None]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for key, value in raw_row.items():
        if key is None:
            continue
        normalized[normalize_header(key)] = "" if value is None else value.strip()
    return normalized


def normalize_header(header: str) -> str:
    return re.sub(r"[^a-z0-9]", "", header.lower())


def is_blank_row(raw_row: dict[str, str | None]) -> bool:
    return all(value is None or not value.strip() for value in raw_row.values())


def required_value(normalized_row: dict[str, str], canonical_name: str, line_number: int) -> str:
    value = optional_value(normalized_row, FIELD_ALIASES[canonical_name])
    if not value:
        pretty = canonical_name.replace("_", " ")
        raise CsvValidationError(f"Line {line_number}: missing required {pretty}")
    return value


def optional_value(normalized_row: dict[str, str], aliases: tuple[str, ...]) -> str:
    for alias in aliases:
        value = normalized_row.get(normalize_header(alias), "")
        if value:
            return value
    return ""


def normalize_coffee_type(value: str, line_number: int) -> str:
    coffee_type = re.sub(r"[^A-Za-z0-9]+", "_", value.strip()).upper().strip("_")
    if coffee_type not in COFFEE_TYPES:
        allowed = ", ".join(sorted(COFFEE_TYPES))
        raise CsvValidationError(
            f"Line {line_number}: coffee type {value!r} is not supported. Allowed: {allowed}"
        )
    return coffee_type


def parse_price(value: str, line_number: int) -> Decimal:
    try:
        price = Decimal(value)
    except InvalidOperation as exc:
        raise CsvValidationError(f"Line {line_number}: price {value!r} is not a number") from exc

    if not price.is_finite():
        raise CsvValidationError(f"Line {line_number}: price must be finite")
    if price <= 0:
        raise CsvValidationError(f"Line {line_number}: price must be greater than zero")

    scale = max(0, -price.as_tuple().exponent)
    if scale > 2:
        raise CsvValidationError(f"Line {line_number}: price may have at most 2 decimal places")

    exponent = price.as_tuple().exponent
    integer_digits = len(price.as_tuple().digits) + max(0, exponent) - scale
    integer_digits = max(0, integer_digits)
    if integer_digits > 10:
        raise CsvValidationError(f"Line {line_number}: price may have at most 10 integer digits")

    return price.quantize(Decimal("0.01"))


def normalize_currency(value: str, line_number: int) -> str:
    currency = value.strip().upper()
    if not re.fullmatch(r"[A-Z]{3}", currency):
        raise CsvValidationError(f"Line {line_number}: currency must be a 3-letter ISO-4217 code")
    return currency


def explicit_idempotency_key(normalized_row: dict[str, str]) -> str:
    key = optional_value(normalized_row, FIELD_ALIASES["idempotency_key"])
    if key:
        return key

    reference = optional_value(normalized_row, UNIQUE_REFERENCE_ALIASES)
    if reference:
        return f"coffee-place:{reference}"

    return ""


def derive_idempotency_key(
    *,
    source_id: str,
    line_number: int,
    store_id: str,
    coffee_type: str,
    price: Decimal,
    currency: str,
    loyalty_card_id: str,
    normalized_row: dict[str, str],
) -> str:
    canonical = "|".join(
        [
            source_id,
            str(line_number),
            store_id,
            coffee_type,
            format_price(price),
            currency,
            loyalty_card_id,
            json.dumps(normalized_row, sort_keys=True),
        ]
    )
    return str(uuid.uuid5(CSV_NAMESPACE, canonical))


def payment_body(row: PaymentRow) -> bytes:
    # Keep price as a JSON number while preserving the validated two-decimal text.
    body = (
        "{"
        f'"coffeeType":{json.dumps(row.coffee_type)},'
        f'"price":{format_price(row.price)},'
        f'"currency":{json.dumps(row.currency)},'
        f'"loyaltyCardId":{json.dumps(row.loyalty_card_id)}'
        "}"
    )
    return body.encode("utf-8")


def format_price(price: Decimal) -> str:
    return format(price, ".2f")


def post_payment(base_url: str, row: PaymentRow, timeout: float) -> PaymentResult:
    url = base_url.rstrip("/") + API_PATH
    request = urllib.request.Request(
        url,
        data=payment_body(row),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Store-Id": row.store_id,
            "Idempotency-Key": row.idempotency_key,
            "User-Agent": "coffee-payments-sync/1.0",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = response.getcode()
            raw_body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        if is_retryable_status(exc.code):
            raise TransientPaymentError(f"HTTP {exc.code}: {body}") from exc
        raise PermanentPaymentError(f"HTTP {exc.code}: {body}") from exc
    except (
        TimeoutError,
        urllib.error.URLError,
        socket.timeout,
        ConnectionError,
        http.client.HTTPException,
    ) as exc:
        raise TransientPaymentError(str(exc)) from exc

    if status not in (200, 201):
        if is_retryable_status(status):
            raise TransientPaymentError(f"HTTP {status}: {raw_body}")
        raise PermanentPaymentError(f"HTTP {status}: {raw_body}")

    try:
        body = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise TransientPaymentError(f"Response was not valid JSON: {raw_body!r}") from exc

    return PaymentResult(http_status=status, body=body)


def is_retryable_status(status: int) -> bool:
    return status in {408, 425, 429} or 500 <= status <= 599


def send_with_retries(
    base_url: str,
    row: PaymentRow,
    *,
    timeout: float,
    max_attempts: int,
    retry_delay: float,
    max_retry_delay: float,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[PaymentResult, int]:
    attempts = 0
    while True:
        attempts += 1
        try:
            return post_payment(base_url, row, timeout), attempts
        except PermanentPaymentError:
            raise
        except TransientPaymentError:
            if attempts >= max_attempts:
                raise

            delay = min(max_retry_delay, retry_delay * (2 ** (attempts - 1)))
            if delay > 0:
                sleep(delay + random.uniform(0, delay * 0.25))


def sync_payments(
    csv_path: Path,
    *,
    base_url: str,
    state_file: Path | None = None,
    source_id: str | None = None,
    timeout: float = 10.0,
    max_attempts: int = 5,
    retry_delay: float = 0.5,
    max_retry_delay: float = 8.0,
    dry_run: bool = False,
    force: bool = False,
    fail_fast: bool = False,
    sleep: Callable[[float], None] = time.sleep,
) -> SyncSummary:
    if max_attempts < 1:
        raise CsvValidationError("max attempts must be at least 1")

    rows = parse_csv(csv_path, source_id=source_id)
    journal = SyncJournal(state_file or default_state_file(csv_path))
    summary = SyncSummary(total=len(rows), dry_run=dry_run)

    for row in rows:
        if journal.is_sent(row) and not force:
            summary.skipped += 1
            continue

        if dry_run:
            summary.sent += 1
            continue

        try:
            result, attempts = send_with_retries(
                base_url,
                row,
                timeout=timeout,
                max_attempts=max_attempts,
                retry_delay=retry_delay,
                max_retry_delay=max_retry_delay,
                sleep=sleep,
            )
            journal.mark_sent(row, result, attempts)
            summary.sent += 1
            summary.retried += max(0, attempts - 1)
        except (TransientPaymentError, PermanentPaymentError) as exc:
            attempts = max_attempts if isinstance(exc, TransientPaymentError) else 1
            message = f"Line {row.line_number}: {exc}"
            summary.failed += 1
            summary.failures.append(message)
            journal.mark_failed(row, message, attempts)
            if fail_fast:
                break

    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Reliably send Coffee Place payment CSV rows to the StarHarbour payments API."
    )
    parser.add_argument("csv_file", nargs="?", type=Path, help="CSV file exported from the notebook")
    parser.add_argument(
        "--base-url",
        default=os.environ.get("PAYMENTS_BASE_URL", "http://localhost:8080"),
        help="External system base URL; defaults to PAYMENTS_BASE_URL or http://localhost:8080",
    )
    parser.add_argument("--state-file", type=Path, help="Sync journal path; defaults next to the CSV")
    parser.add_argument(
        "--source-id",
        help="Stable source name used when deriving idempotency keys; defaults to the CSV filename",
    )
    parser.add_argument("--timeout", type=float, default=10.0, help="Per-request timeout in seconds")
    parser.add_argument("--max-attempts", type=int, default=5, help="Total attempts per row")
    parser.add_argument("--retry-delay", type=float, default=0.5, help="Initial retry delay in seconds")
    parser.add_argument("--max-retry-delay", type=float, default=8.0, help="Maximum retry delay in seconds")
    parser.add_argument("--dry-run", action="store_true", help="Validate and show what would be sent")
    parser.add_argument("--force", action="store_true", help="Send rows even if the journal marks them sent")
    parser.add_argument("--fail-fast", action="store_true", help="Stop after the first failed row")
    parser.add_argument("--list-coffee-types", action="store_true", help="Print accepted coffee types and exit")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.list_coffee_types:
        for coffee_type in sorted(COFFEE_TYPES):
            print(coffee_type)
        return 0

    if args.csv_file is None:
        parser.error("csv_file is required unless --list-coffee-types is used")

    try:
        summary = sync_payments(
            args.csv_file,
            base_url=args.base_url,
            state_file=args.state_file,
            source_id=args.source_id,
            timeout=args.timeout,
            max_attempts=args.max_attempts,
            retry_delay=args.retry_delay,
            max_retry_delay=args.max_retry_delay,
            dry_run=args.dry_run,
            force=args.force,
            fail_fast=args.fail_fast,
        )
    except CsvValidationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    verb = "would send" if summary.dry_run else "sent"
    print(
        f"{summary.total} row(s): {summary.sent} {verb}, "
        f"{summary.skipped} skipped, {summary.failed} failed, {summary.retried} retried"
    )
    if summary.failures:
        for failure in summary.failures:
            print(f"error: {failure}", file=sys.stderr)

    return 0 if summary.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
