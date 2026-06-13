import threading
import time
import unittest

from loadbalancer.health import HealthChecker
from loadbalancer.registry import BackendPool


class HealthCheckerTest(unittest.TestCase):
    def test_check_once_drives_pool_state(self):
        pool = BackendPool(["a", "b"], fail_threshold=2, rise_threshold=1)
        up = {"a": True, "b": False}
        checker = HealthChecker(pool, probe=lambda url: up[url])

        checker.check_once()
        checker.check_once()  # b now has two failures

        healthy = {b.url for b in pool.healthy()}
        self.assertEqual(healthy, {"a"})

    def test_recovery_is_picked_up(self):
        pool = BackendPool(["a"], fail_threshold=1, rise_threshold=2)
        state = {"up": False}
        checker = HealthChecker(pool, probe=lambda url: state["up"])

        checker.check_once()
        self.assertEqual(pool.healthy(), [])
        state["up"] = True
        checker.check_once()
        checker.check_once()
        self.assertEqual({b.url for b in pool.healthy()}, {"a"})

    def test_background_thread_runs_checks(self):
        pool = BackendPool(["a"])
        ticks = {"n": 0}
        event = threading.Event()

        def probe(url):
            ticks["n"] += 1
            event.set()
            return True

        checker = HealthChecker(pool, probe=probe, interval=0.05)
        checker.start()
        self.assertTrue(event.wait(timeout=2))  # at least the startup probe ran
        time.sleep(0.12)
        checker.stop()
        self.assertGreaterEqual(ticks["n"], 2)  # startup + at least one loop tick


if __name__ == "__main__":
    unittest.main()
