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
