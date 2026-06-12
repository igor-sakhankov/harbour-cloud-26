from __future__ import annotations

import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from coffee_payments_sync import CsvValidationError, parse_csv, sync_payments


class RecordingHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        length = int(self.headers["Content-Length"])
        body = self.rfile.read(length).decode("utf-8")
        record = {
            "path": self.path,
            "headers": dict(self.headers),
            "body": json.loads(body),
        }
        self.server.records.append(record)  # type: ignore[attr-defined]

        status = self.server.statuses.pop(0) if self.server.statuses else 201  # type: ignore[attr-defined]
        if status >= 400:
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error":"temporary"}')
            return

        response = {
            "paymentId": f"payment-{len(self.server.records)}",  # type: ignore[attr-defined]
            "storeId": record["headers"]["Store-Id"],
            "coffeeType": record["body"]["coffeeType"],
            "price": record["body"]["price"],
            "currency": record["body"]["currency"],
            "loyaltyCardId": record["body"]["loyaltyCardId"],
            "registeredAt": "2026-06-12T00:00:00Z",
        }
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(response).encode("utf-8"))

    def log_message(self, format: str, *args: object) -> None:
        return


class MockPaymentServer:
    def __init__(self, statuses: list[int] | None = None):
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), RecordingHandler)
        self.httpd.records = []  # type: ignore[attr-defined]
        self.httpd.statuses = list(statuses or [])  # type: ignore[attr-defined]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def __enter__(self) -> "MockPaymentServer":
        self.thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.httpd.shutdown()
        self.thread.join()
        self.httpd.server_close()

    @property
    def base_url(self) -> str:
        host, port = self.httpd.server_address
        return f"http://{host}:{port}"

    @property
    def records(self) -> list[dict[str, object]]:
        return self.httpd.records  # type: ignore[attr-defined]


class CoffeePaymentsSyncTest(unittest.TestCase):
    def test_posts_valid_payment_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, MockPaymentServer() as server:
            csv_path = Path(tmp) / "payments.csv"
            state_path = Path(tmp) / "state.json"
            csv_path.write_text(
                "store_id,coffee_type,price,currency,loyalty_card_id,idempotency_key\n"
                "store-bkk-01,latte,3.50,eur,card-123,key-1\n",
                encoding="utf-8",
            )

            summary = sync_payments(
                csv_path,
                base_url=server.base_url,
                state_file=state_path,
                retry_delay=0,
            )

            self.assertEqual(summary.sent, 1)
            self.assertEqual(summary.failed, 0)
            self.assertEqual(len(server.records), 1)
            request = server.records[0]
            self.assertEqual(request["path"], "/api/v1/payments")
            self.assertEqual(request["headers"]["Store-Id"], "store-bkk-01")
            self.assertEqual(request["headers"]["Idempotency-Key"], "key-1")
            self.assertEqual(request["body"]["coffeeType"], "LATTE")
            self.assertEqual(request["body"]["price"], 3.5)
            self.assertEqual(request["body"]["currency"], "EUR")

    def test_second_run_skips_rows_already_marked_sent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, MockPaymentServer() as server:
            csv_path = Path(tmp) / "payments.csv"
            state_path = Path(tmp) / "state.json"
            csv_path.write_text(
                "store_id,coffee_type,price,currency,loyalty_card_id,transaction_id\n"
                "store-bkk-01,cappuccino,4,USD,card-456,txn-456\n",
                encoding="utf-8",
            )

            first = sync_payments(csv_path, base_url=server.base_url, state_file=state_path)
            second = sync_payments(csv_path, base_url=server.base_url, state_file=state_path)

            self.assertEqual(first.sent, 1)
            self.assertEqual(second.sent, 0)
            self.assertEqual(second.skipped, 1)
            self.assertEqual(len(server.records), 1)

    def test_retries_transient_failure_with_same_idempotency_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, MockPaymentServer([500, 201]) as server:
            csv_path = Path(tmp) / "payments.csv"
            state_path = Path(tmp) / "state.json"
            csv_path.write_text(
                "store_id,coffee_type,price,currency,loyalty_card_id,idempotency_key\n"
                "store-bkk-01,flat white,4.25,GBP,card-789,retry-key\n",
                encoding="utf-8",
            )

            summary = sync_payments(
                csv_path,
                base_url=server.base_url,
                state_file=state_path,
                retry_delay=0,
                max_attempts=2,
            )

            self.assertEqual(summary.sent, 1)
            self.assertEqual(summary.retried, 1)
            self.assertEqual(len(server.records), 2)
            keys = {record["headers"]["Idempotency-Key"] for record in server.records}
            self.assertEqual(keys, {"retry-key"})

    def test_validation_rejects_bad_currency_before_http(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "payments.csv"
            csv_path.write_text(
                "store_id,coffee_type,price,currency,loyalty_card_id\n"
                "store-bkk-01,latte,3.50,euro,card-123\n",
                encoding="utf-8",
            )

            with self.assertRaises(CsvValidationError):
                parse_csv(csv_path)

    def test_validation_rejects_prices_with_too_many_integer_digits(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "payments.csv"
            csv_path.write_text(
                "store_id,coffee_type,price,currency,loyalty_card_id\n"
                "store-bkk-01,latte,1E+11,EUR,card-123\n",
                encoding="utf-8",
            )

            with self.assertRaises(CsvValidationError):
                parse_csv(csv_path)


if __name__ == "__main__":
    unittest.main()
