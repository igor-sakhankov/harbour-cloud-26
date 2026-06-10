import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent))

import uploader


#Helpers

SAMPLE_ORDER = {
    "order_id":       "order-test-01",
    "coffee_type":    "LATTE",
    "price":          "3.50",
    "currency":       "EUR",
    "loyalty_card_id": "card-001",
}


def make_http_response(status: int):
    mock = MagicMock()
    mock.status = status
    mock.__enter__ = lambda s: s
    mock.__exit__  = MagicMock(return_value=False)
    return mock


#Unit tests 

class TestSendPayment(unittest.TestCase):

    @patch("urllib.request.urlopen")
    def test_returns_201_on_new_payment(self, mock_urlopen):
        mock_urlopen.return_value = make_http_response(201)
        status = uploader.send_payment("http://localhost:8080", "store-1", SAMPLE_ORDER)
        self.assertEqual(status, 201)

    @patch("urllib.request.urlopen")
    def test_returns_200_on_duplicate_idempotency_key(self, mock_urlopen):
        mock_urlopen.return_value = make_http_response(200)
        status = uploader.send_payment("http://localhost:8080", "store-1", SAMPLE_ORDER)
        self.assertEqual(status, 200)

    @patch("urllib.request.urlopen")
    def test_returns_400_on_bad_request(self, mock_urlopen):
        import urllib.error
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url=None, code=400, msg="Bad Request", hdrs=None, fp=None
        )
        status = uploader.send_payment("http://localhost:8080", "store-1", SAMPLE_ORDER)
        self.assertEqual(status, 400)


class TestUploadWithRetry(unittest.TestCase):

    @patch("uploader.send_payment", return_value=201)
    def test_succeeds_on_first_attempt(self, _mock):
        result = uploader.upload_with_retry("http://localhost:8080", "store-1", SAMPLE_ORDER)
        self.assertTrue(result)

    @patch("uploader.send_payment", return_value=200)
    def test_idempotent_replay_counts_as_success(self, _mock):
        result = uploader.upload_with_retry("http://localhost:8080", "store-1", SAMPLE_ORDER)
        self.assertTrue(result)

    @patch("uploader.send_payment", return_value=400)
    def test_client_error_is_not_retried(self, mock_send):
        result = uploader.upload_with_retry("http://localhost:8080", "store-1", SAMPLE_ORDER)
        self.assertFalse(result)
        self.assertEqual(mock_send.call_count, 1)   # gave up immediately

    @patch("uploader.time.sleep")   # prevent real sleeping
    @patch("uploader.send_payment", return_value=500)
    def test_retries_on_server_error_then_fails(self, mock_send, _mock_sleep):
        result = uploader.upload_with_retry("http://localhost:8080", "store-1", SAMPLE_ORDER)
        self.assertFalse(result)
        self.assertEqual(mock_send.call_count, uploader.MAX_RETRIES)

    @patch("uploader.time.sleep")
    @patch("uploader.send_payment", side_effect=[500, 500, 201])
    def test_succeeds_after_two_failures(self, mock_send, _mock_sleep):
        result = uploader.upload_with_retry("http://localhost:8080", "store-1", SAMPLE_ORDER)
        self.assertTrue(result)
        self.assertEqual(mock_send.call_count, 3)


class TestSentOrdersTracking(unittest.TestCase):

    def test_load_returns_empty_set_when_file_missing(self):
        sent = uploader.load_sent_orders("/nonexistent/path.json")
        self.assertEqual(sent, set())

    def test_save_and_load_round_trip(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name

        sent = {"order-001", "order-002"}
        uploader.save_sent_orders(path, sent)
        loaded = uploader.load_sent_orders(path)
        self.assertEqual(loaded, sent)


class TestCSVReading(unittest.TestCase):

    def test_reads_csv_correctly(self):
        import csv, io
        raw = "order_id,coffee_type,price,currency,loyalty_card_id\n" \
              "order-001,LATTE,3.50,EUR,card-001\n"
        reader = csv.DictReader(io.StringIO(raw))
        rows = list(reader)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["coffee_type"], "LATTE")
        self.assertEqual(rows[0]["price"], "3.50")


if __name__ == "__main__":
    unittest.main()