import unittest

from coffee_sync.client import PaymentClient, SendResult
from coffee_sync.parser import PaymentRow
from tests._fake_server import FakeCentral


def row(row_number=2, idem="key-1"):
    return PaymentRow(
        store_id="STORE1", coffee_type="LATTE", price="3.50",
        currency="EUR", loyalty_card_id="card-1",
        row_number=row_number, idempotency_key=idem,
    )


# Zero backoff base keeps tests fast.
def client(base_url, **kw):
    return PaymentClient(base_url=base_url, timeout=1.0, max_retries=5,
                         backoff_base=0.0, backoff_cap=0.0, **kw)


class PaymentClientTest(unittest.TestCase):
    def test_new_payment_returns_created(self):
        with FakeCentral() as srv:
            res = client(srv.base_url).send(row())
            self.assertEqual(res.outcome, "created")
            self.assertEqual(res.payment_id, "pay-1")
            self.assertEqual(srv.created_count, 1)

    def test_same_key_replays_as_200(self):
        with FakeCentral() as srv:
            c = client(srv.base_url)
            first = c.send(row(idem="dup"))
            second = c.send(row(idem="dup"))
            self.assertEqual(first.outcome, "created")
            self.assertEqual(second.outcome, "replayed")
            self.assertEqual(second.payment_id, first.payment_id)
            self.assertEqual(srv.created_count, 1)

    def test_retries_500_then_succeeds(self):
        with FakeCentral(fail_times=2, fail_mode="500") as srv:
            res = client(srv.base_url).send(row())
            self.assertEqual(res.outcome, "created")
            self.assertEqual(srv.requests_seen, 3)  # 2 failures + 1 success

    def test_retry_after_lost_response_does_not_duplicate(self):
        # Server succeeds but first response is "lost" via a timeout; the stable
        # idempotency key means the retry replays instead of creating a second.
        with FakeCentral(fail_times=1, fail_mode="timeout", fail_delay=2.0) as srv:
            res = client(srv.base_url).send(row(idem="lost"))
            self.assertIn(res.outcome, ("created", "replayed"))
            self.assertEqual(srv.created_count, 1)

    def test_400_is_not_retried_and_reports_detail(self):
        with FakeCentral() as srv:
            bad = PaymentRow(
                store_id="STORE1", coffee_type="LATTE", price="",
                currency="EUR", loyalty_card_id="c",
                row_number=2, idempotency_key="bad",
            )
            res = client(srv.base_url).send(bad)
            self.assertEqual(res.outcome, "failed")
            self.assertIn("price", res.detail)
            self.assertEqual(srv.requests_seen, 1)  # not retried

    def test_exhausted_retries_returns_failed(self):
        with FakeCentral(fail_times=99, fail_mode="500") as srv:
            res = client(srv.base_url).send(row())
            self.assertEqual(res.outcome, "failed")
            self.assertEqual(srv.requests_seen, 5)  # max_retries attempts


if __name__ == "__main__":
    unittest.main()
