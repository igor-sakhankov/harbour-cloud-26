"""
Generate a fake "end-of-day notebook" of coffee payments as a CSV.

Mirrors the StarHarbour Payments API contract:
  - coffee_type  -> one of CoffeeType (server enum)
  - price        -> > 0, at most 2 decimal places
  - currency     -> 3-letter ISO-4217 code
  - loyalty_card_id, store_id, order_id (used as the Idempotency-Key)

A few intentionally-invalid rows are appended so the notebook can show how the
reliable client distinguishes non-retryable 400s (bad data) from retryable
network faults.

Usage:
    python generate_csv.py --rows 40 --out payments.csv
"""
import argparse
import csv
import random

from faker import Faker

COFFEE_TYPES = [
    "ESPRESSO", "DOUBLE_ESPRESSO", "AMERICANO", "LATTE", "CAPPUCCINO",
    "FLAT_WHITE", "MOCHA", "CORTADO", "MACCHIATO", "COLD_BREW",
]

STORES = [
    ("store-london-01", "GBP"),
    ("store-berlin-02", "EUR"),
    ("store-madrid-03", "EUR"),
]


def valid_row(fake: Faker, order_id: str) -> dict:
    store_id, currency = random.choice(STORES)
    return {
        "order_id": order_id,
        "store_id": store_id,
        "coffee_type": random.choice(COFFEE_TYPES),
        "price": f"{random.uniform(1.5, 4.5):.2f}",
        "currency": currency,
        "loyalty_card_id": f"card-{fake.bothify('????-####').lower()}",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=40)
    parser.add_argument("--out", default="payments.csv")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    random.seed(args.seed)
    fake = Faker()
    Faker.seed(args.seed)

    rows = [valid_row(fake, f"ord-{1000 + i}") for i in range(args.rows)]

    # Three deliberately-invalid rows -> server should answer 400 (non-retryable).
    rows.append({"order_id": "ord-9001", "store_id": "store-london-01",
                 "coffee_type": "LATTE", "price": "0.00", "currency": "GBP",
                 "loyalty_card_id": "card-bad-001"})          # price must be > 0
    rows.append({"order_id": "ord-9002", "store_id": "store-berlin-02",
                 "coffee_type": "UNICORN_BREW", "price": "3.00", "currency": "EUR",
                 "loyalty_card_id": "card-bad-002"})          # unknown coffee type
    rows.append({"order_id": "ord-9003", "store_id": "store-madrid-03",
                 "coffee_type": "ESPRESSO", "price": "1.60", "currency": "eur",
                 "loyalty_card_id": "card-bad-003"})          # currency not [A-Z]{3}

    fieldnames = ["order_id", "store_id", "coffee_type", "price", "currency", "loyalty_card_id"]
    with open(args.out, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} rows to {args.out} ({len(rows) - 3} valid, 3 invalid).")


if __name__ == "__main__":
    main()
