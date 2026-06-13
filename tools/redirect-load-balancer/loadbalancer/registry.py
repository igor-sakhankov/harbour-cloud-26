"""Keeps the list of backends and their health, and hands out the next healthy
one in round-robin order. Round-robin is a good fit here: a redirect LB treats
every request independently and never sees the connection afterwards, so
connection-aware schemes (least-connections) don't apply. All access is locked
because the health checker thread and the request threads touch it at once."""

from __future__ import annotations

import threading
from dataclasses import dataclass


@dataclass
class Backend:
    url: str
    healthy: bool = True
    fails: int = 0
    oks: int = 0


class BackendPool:
    def __init__(self, urls, fail_threshold=2, rise_threshold=2, start_healthy=True):
        self._backends = [Backend(u, healthy=start_healthy) for u in urls]
        self._fail_threshold = fail_threshold
        self._rise_threshold = rise_threshold
        self._lock = threading.Lock()
        self._cursor = 0

    def all(self):
        with self._lock:
            return list(self._backends)

    def healthy(self):
        with self._lock:
            return [b for b in self._backends if b.healthy]

    def next_healthy(self):
        """Next healthy backend in round-robin order, or None if none is healthy."""
        with self._lock:
            healthy = [b for b in self._backends if b.healthy]
            if not healthy:
                return None
            backend = healthy[self._cursor % len(healthy)]
            self._cursor += 1
            return backend

    def record_health(self, url, ok):
        """Feed one probe result in. A healthy backend flips to unhealthy after
        fail_threshold consecutive failures; an unhealthy one flips back after
        rise_threshold consecutive successes."""
        with self._lock:
            for backend in self._backends:
                if backend.url == url:
                    self._apply(backend, ok)
                    return

    def _apply(self, backend, ok):
        if ok:
            backend.oks += 1
            backend.fails = 0
            if not backend.healthy and backend.oks >= self._rise_threshold:
                backend.healthy = True
        else:
            backend.fails += 1
            backend.oks = 0
            if backend.healthy and backend.fails >= self._fail_threshold:
                backend.healthy = False
