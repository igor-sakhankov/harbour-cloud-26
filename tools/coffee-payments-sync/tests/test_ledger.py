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
