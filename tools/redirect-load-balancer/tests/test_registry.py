import unittest

from loadbalancer.registry import BackendPool


class RoundRobinTest(unittest.TestCase):
    def test_cycles_through_all_healthy(self):
        pool = BackendPool(["a", "b", "c"])
        picks = [pool.next_healthy().url for _ in range(6)]
        self.assertEqual(picks, ["a", "b", "c", "a", "b", "c"])

    def test_skips_unhealthy(self):
        pool = BackendPool(["a", "b", "c"], fail_threshold=1)
        pool.record_health("b", False)  # b out after one failure
        picks = [pool.next_healthy().url for _ in range(4)]
        self.assertEqual(picks, ["a", "c", "a", "c"])

    def test_none_when_all_unhealthy(self):
        pool = BackendPool(["a", "b"], fail_threshold=1)
        pool.record_health("a", False)
        pool.record_health("b", False)
        self.assertIsNone(pool.next_healthy())


class HealthTransitionTest(unittest.TestCase):
    def _only(self, pool, url):
        return next(b for b in pool.all() if b.url == url)

    def test_drops_after_fail_threshold(self):
        pool = BackendPool(["a"], fail_threshold=2)
        pool.record_health("a", False)
        self.assertTrue(self._only(pool, "a").healthy)   # one failure: still in
        pool.record_health("a", False)
        self.assertFalse(self._only(pool, "a").healthy)  # second: dropped

    def test_a_success_resets_the_failure_streak(self):
        pool = BackendPool(["a"], fail_threshold=2)
        pool.record_health("a", False)
        pool.record_health("a", True)
        pool.record_health("a", False)
        self.assertTrue(self._only(pool, "a").healthy)   # streak broken, still in

    def test_recovers_after_rise_threshold(self):
        pool = BackendPool(["a"], fail_threshold=1, rise_threshold=2)
        pool.record_health("a", False)
        self.assertFalse(self._only(pool, "a").healthy)
        pool.record_health("a", True)
        self.assertFalse(self._only(pool, "a").healthy)  # one success isn't enough
        pool.record_health("a", True)
        self.assertTrue(self._only(pool, "a").healthy)   # second brings it back


if __name__ == "__main__":
    unittest.main()
