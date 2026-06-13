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
