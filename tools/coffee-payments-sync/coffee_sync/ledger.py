"""Append-only JSONL ledger of confirmed payments. Enables safe resume: a row
whose idempotency key is already recorded is skipped on the next run. Append +
flush per line keeps it crash-safe — at most the in-flight line is lost, and the
stable idempotency key makes resending that row safe."""

from __future__ import annotations

import json
import os


class Ledger:
    def __init__(self, path):
        self.path = path

    def confirmed_keys(self):
        """Set of idempotency keys already confirmed. Tolerates a corrupt final
        line from a crash mid-write by skipping unparseable lines."""
        keys = set()
        if not os.path.exists(self.path):
            return keys
        with open(self.path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    keys.add(json.loads(line)["idempotency_key"])
                except (ValueError, KeyError):
                    continue
        return keys

    def record(self, idempotency_key, payment_id, status):
        """Append one confirmed payment and flush to disk immediately."""
        entry = {
            "idempotency_key": idempotency_key,
            "payment_id": payment_id,
            "status": status,
        }
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
