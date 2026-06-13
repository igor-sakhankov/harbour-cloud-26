"""Active health checking. A background thread probes every backend on an
interval and feeds the result into the pool. The probe is a plain callable so
tests can inject a fake one instead of doing real HTTP."""

from __future__ import annotations

import threading
import urllib.error
import urllib.request


def http_probe(url, health_path, timeout):
    """Return True if GET url+health_path answers with a 2xx within timeout."""
    try:
        with urllib.request.urlopen(url + health_path, timeout=timeout) as resp:
            return 200 <= resp.status < 300
    except (urllib.error.URLError, OSError, ValueError):
        return False


class HealthChecker:
    def __init__(self, pool, probe, interval=1.0):
        self._pool = pool
        self._probe = probe          # callable(url) -> bool
        self._interval = interval
        self._stop = threading.Event()
        self._thread = None

    def check_once(self):
        for backend in self._pool.all():
            self._pool.record_health(backend.url, self._probe(backend.url))

    def start(self):
        self.check_once()            # probe immediately so we're current at startup
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return self

    def _loop(self):
        while not self._stop.wait(self._interval):
            self.check_once()

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
