import threading
import time
import unittest
import urllib.request

from loadbalancer.health import HealthChecker, http_probe
from loadbalancer.registry import BackendPool
from loadbalancer.server import make_server
from tests._fake_backend import FakeBackend

HEALTH_PATH = "/api/v1/payments?storeId=__lb_health__"


class IntegrationTest(unittest.TestCase):
    def setUp(self):
        self.b1 = FakeBackend("b1").start()
        self.b2 = FakeBackend("b2").start()
        self.addCleanup(self.b1.stop)
        self.addCleanup(self.b2.stop)

        self.pool = BackendPool([self.b1.url, self.b2.url], fail_threshold=2, rise_threshold=1)
        probe = lambda url: http_probe(url, HEALTH_PATH, timeout=1.0)
        self.checker = HealthChecker(self.pool, probe, interval=0.1).start()
        self.addCleanup(self.checker.stop)

        self.server = make_server(self.pool, "127.0.0.1", 0)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(lambda: (self.server.shutdown(), self.server.server_close()))
        host, port = self.server.server_address
        self.lb = f"http://{host}:{port}"

    def _call(self):
        with urllib.request.urlopen(self.lb + "/api/v1/payments?storeId=x", timeout=5) as resp:
            return resp.read().decode()  # body is the backend's name

    def _wait_healthy(self, count, timeout=3.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if len(self.pool.healthy()) == count:
                return
            time.sleep(0.05)
        self.fail(f"expected {count} healthy backends, got {len(self.pool.healthy())}")

    def test_requests_spread_across_both_backends(self):
        self._wait_healthy(2)
        self.checker.stop()            # stop probes so only real load is counted
        self.b1.hits = self.b2.hits = 0
        for _ in range(10):
            self._call()
        self.assertGreater(self.b1.hits, 0)
        self.assertGreater(self.b2.hits, 0)
        self.assertEqual(self.b1.hits + self.b2.hits, 10)

    def test_failover_when_a_backend_dies(self):
        self._wait_healthy(2)
        self.b2.stop()                 # b2 goes away
        self._wait_healthy(1)          # health checker drops it
        self.b1.hits = self.b2.hits = 0
        for _ in range(6):
            self.assertEqual(self._call(), "b1")
        self.assertEqual(self.b1.hits, 6)
        self.assertEqual(self.b2.hits, 0)


if __name__ == "__main__":
    unittest.main()
