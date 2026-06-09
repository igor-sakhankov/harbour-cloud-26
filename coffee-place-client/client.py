#!/usr/bin/env python3
import argparse
import csv
import json
import sys
import time
import uuid
from dataclasses import dataclass
from urllib import request, error

# Same set the server's CoffeeType enum accepts.
VALID_COFFEE_TYPES = {
    "ESPRESSO", "DOUBLE_ESPRESSO", "AMERICANO", "LATTE", "CAPPUCCINO",
    "FLAT_WHITE", "MOCHA", "CORTADO", "MACCHIATO", "COLD_BREW",
}

# Namespace for deterministic idempotency keys. A fixed UUID so the same row
# always maps to the same key, even across separate runs of this script.
IDEMPOTENCY_NAMESPACE = uuid.UUID("6f9619ff-8b86-d011-b42d-00cf4fc964ff")


@dataclass
class Row:
    line_no: int
    coffee_type: str
    price: str
    currency: str
    loyalty_card_id: str
    idempotency_key: str 


class ValidationError(Exception):
    pass


def parse_row(raw: dict, line_no: int) -> Row:
    """Pull the expected columns out of a CSV record, trimming whitespace."""
    def get(key: str) -> str:
        return (raw.get(key) or "").strip()

    return Row(
        line_no=line_no,
        coffee_type=get("coffeeType").upper(),
        price=get("price"),
        currency=get("currency").upper(),
        loyalty_card_id=get("loyaltyCardId"),
        idempotency_key=get("idempotencyKey"),
    )


def validate(row: Row) -> dict:
    """Validate a row against the server contract; return the JSON body
    """
    if row.coffee_type not in VALID_COFFEE_TYPES:
        raise ValidationError(
            f"coffeeType '{row.coffee_type}' is not one of {sorted(VALID_COFFEE_TYPES)}"
        )

    try:
        price = float(row.price)
    except ValueError:
        raise ValidationError(f"price '{row.price}' is not a number")
    if price <= 0:
        raise ValidationError("price must be greater than zero")
    # Server allows at most 2 decimal places.
    if "." in row.price and len(row.price.split(".", 1)[1]) > 2:
        raise ValidationError("price may have at most 2 decimal places")

    if not (len(row.currency) == 3 and row.currency.isalpha()):
        raise ValidationError(
            f"currency '{row.currency}' must be a 3-letter code, e.g. EUR"
        )

    if not row.loyalty_card_id:
        raise ValidationError("loyaltyCardId is required")

    return {
        "coffeeType": row.coffee_type,
        "price": price,
        "currency": row.currency,
        "loyaltyCardId": row.loyalty_card_id,
    }


def idempotency_key_for(row: Row, store_id: str) -> str:
    """Stable key per logical payment.

    If the CSV supplies its own key we trust it. Otherwise we derive a
    deterministic UUIDv5 from the store, the line number and the row contents.
    Including the line number keeps two identical coffees on different rows as
    two distinct payments, while re-running the same file reproduces the same
    keys -> no duplicates on the server.
    """
    if row.idempotency_key:
        return row.idempotency_key
    seed = f"{store_id}:{row.line_no}:{row.coffee_type}:{row.price}:{row.currency}:{row.loyalty_card_id}"
    return str(uuid.uuid5(IDEMPOTENCY_NAMESPACE, seed))


@dataclass
class SendResult:
    status: int          # HTTP status, or 0 if all attempts failed
    created: bool        # 201
    duplicate: bool      # 200 (idempotent replay)
    attempts: int
    error: str = ""


def send_payment(
    base_url: str,
    store_id: str,
    body: dict,
    idempotency_key: str,
    timeout: float,
    max_attempts: int,
    backoff_base: float,
) -> SendResult:
    """POST a single payment, retrying transient failures with backoff."""
    url = f"{base_url.rstrip('/')}/api/v1/payments"
    payload = json.dumps(body).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Store-Id": store_id,
        "Idempotency-Key": idempotency_key,
    }

    last_error = ""
    for attempt in range(1, max_attempts + 1):
        req = request.Request(url, data=payload, headers=headers, method="POST")
        try:
            with request.urlopen(req, timeout=timeout) as resp:
                status = resp.status
                return SendResult(
                    status=status,
                    created=(status == 201),
                    duplicate=(status == 200),
                    attempts=attempt,
                )
        except error.HTTPError as e:
            status = e.code
            # 4xx (except 429) are our fault: do not retry.
            if 400 <= status < 500 and status != 429:
                detail = e.read().decode("utf-8", "replace")
                return SendResult(
                    status=status, created=False, duplicate=False,
                    attempts=attempt, error=f"HTTP {status}: {detail}",
                )
            last_error = f"HTTP {status}"  # 5xx or 429 -> retry
        except (error.URLError, TimeoutError, ConnectionError) as e:
            last_error = f"{type(e).__name__}: {e}"  # timeout / dropped -> retry

        if attempt < max_attempts:
            delay = backoff_base * (2 ** (attempt - 1))
            # Deterministic jitter (no RNG): spread by key + attempt.
            jitter = (hash((idempotency_key, attempt)) % 100) / 1000.0
            time.sleep(delay + jitter)

    return SendResult(
        status=0, created=False, duplicate=False,
        attempts=max_attempts, error=f"giving up after {max_attempts} attempts: {last_error}",
    )


def run(args) -> int:
    created = duplicates = failed = skipped = 0

    with open(args.csv_file, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for i, raw in enumerate(reader, start=2):  # line 1 is the header
            row = parse_row(raw, i)

            try:
                body = validate(row)
            except ValidationError as e:
                skipped += 1
                print(f"[line {i}] SKIP (invalid): {e}")
                continue

            key = idempotency_key_for(row, args.store_id)
            result = send_payment(
                base_url=args.base_url,
                store_id=args.store_id,
                body=body,
                idempotency_key=key,
                timeout=args.timeout,
                max_attempts=args.max_attempts,
                backoff_base=args.backoff_base,
            )

            if result.created:
                created += 1
                print(f"[line {i}] CREATED ({result.attempts} attempt(s)) {body['coffeeType']} {body['price']} {body['currency']}")
            elif result.duplicate:
                duplicates += 1
                print(f"[line {i}] DUPLICATE -> already processed ({result.attempts} attempt(s))")
            else:
                failed += 1
                print(f"[line {i}] FAILED: {result.error}")

    total = created + duplicates + failed + skipped
    print("\n--- Summary ---")
    print(f"rows read : {total}")
    print(f"created   : {created}")
    print(f"duplicates: {duplicates}")
    print(f"failed    : {failed}")
    print(f"skipped   : {skipped}")

    # Non-zero exit if anything failed, so it's usable in scripts/CI.
    return 1 if failed else 0


def main() -> int:
    p = argparse.ArgumentParser(description="Upload coffee payments from a CSV to the Central System.")
    p.add_argument("csv_file", help="Path to the CSV file of payments")
    p.add_argument("--store-id", required=True, help="Store-Id header value")
    p.add_argument("--base-url", default="http://localhost:9091",
                   help="Service base URL (default: Toxiproxy on :9091; use :8080 to bypass faults)")
    p.add_argument("--timeout", type=float, default=3.0, help="Per-request timeout in seconds")
    p.add_argument("--max-attempts", type=int, default=5, help="Max attempts per payment")
    p.add_argument("--backoff-base", type=float, default=0.5, help="Base backoff in seconds (doubles each retry)")
    args = p.parse_args()

    try:
        return run(args)
    except FileNotFoundError:
        print(f"error: file not found: {args.csv_file}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
