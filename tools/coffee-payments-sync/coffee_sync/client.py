"""Posts a single payment to the API and handles retries.

The same Idempotency-Key is sent on every attempt so a retry after a lost
response replays the original payment (200) rather than creating a duplicate.
Timeouts, connection errors, 429 and 5xx are retried with exponential backoff
and jitter; a 4xx is treated as permanent and reported with the server message.
"""

from __future__ import annotations

import json
import random
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

from .parser import idempotency_key

PAYMENTS_PATH = "/api/v1/payments"


@dataclass(frozen=True)
class SendResult:
    outcome: str        # "created" | "replayed" | "failed"
    idempotency_key: str
    payment_id: str = ""
    detail: str = ""    # failure reason (server message or last error)


class PaymentClient:
    def __init__(self, base_url, timeout=10.0, max_retries=5,
                 backoff_base=0.5, backoff_cap=8.0, sleep=time.sleep,
                 rand=random.random):
        self.url = base_url.rstrip("/") + PAYMENTS_PATH
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.backoff_cap = backoff_cap
        self._sleep = sleep
        self._rand = rand

    def send(self, row):
        key = idempotency_key(row)
        body = json.dumps({
            "coffeeType": row.coffee_type,
            "price": row.price,
            "currency": row.currency,
            "loyaltyCardId": row.loyalty_card_id,
        }).encode("utf-8")

        last_detail = ""
        for attempt in range(self.max_retries):
            if attempt > 0:
                self._backoff(attempt)
            outcome, payment_id, detail, retryable = self._attempt(body, row.store_id, key)
            if outcome != "failed":
                return SendResult(outcome, key, payment_id)
            last_detail = detail
            if not retryable:
                return SendResult("failed", key, detail=detail)
        return SendResult("failed", key, detail=last_detail or "retries exhausted")

    def _attempt(self, body, store_id, key):
        """Returns (outcome, payment_id, detail, retryable)."""
        request = urllib.request.Request(self.url, data=body, method="POST")
        request.add_header("Content-Type", "application/json")
        request.add_header("Store-Id", store_id)
        request.add_header("Idempotency-Key", key)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as resp:
                status = resp.status
                payload = self._read_json(resp.read())
                payment_id = payload.get("paymentId", "")
                return ("created" if status == 201 else "replayed"), payment_id, "", False
        except urllib.error.HTTPError as err:
            detail = self._error_detail(err)
            retryable = err.code == 429 or err.code >= 500
            return "failed", "", detail, retryable
        except (urllib.error.URLError, TimeoutError, OSError) as err:
            return "failed", "", f"network error: {err}", True

    def _backoff(self, attempt):
        delay = min(self.backoff_cap, self.backoff_base * (2 ** (attempt - 1)))
        self._sleep(delay + self._rand() * self.backoff_base)

    @staticmethod
    def _read_json(raw):
        try:
            return json.loads(raw or b"{}")
        except ValueError:
            return {}

    @staticmethod
    def _error_detail(err):
        try:
            payload = json.loads(err.read() or b"{}")
            return payload.get("detail") or f"HTTP {err.code}"
        except (ValueError, OSError):
            return f"HTTP {err.code}"
        finally:
            err.close()
