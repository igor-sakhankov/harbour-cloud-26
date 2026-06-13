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
