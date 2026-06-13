import http.client
import threading
import unittest

from loadbalancer.registry import BackendPool
from loadbalancer.server import make_server


class ServerTest(unittest.TestCase):
    def _serve(self, pool, redirect_status=302):
        server = make_server(pool, "127.0.0.1", 0, redirect_status)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(lambda: (server.shutdown(), server.server_close()))
        return server.server_address  # (host, port)

    def _request(self, addr, path):
        conn = http.client.HTTPConnection(*addr)
        conn.request("GET", path)
        resp = conn.getresponse()
        resp.read()
        location = resp.getheader("Location")
        conn.close()
        return resp.status, location

    def test_302_with_location_preserving_path_and_query(self):
        pool = BackendPool(["http://backend-1:9001"])
        addr = self._serve(pool)
        status, location = self._request(addr, "/api/v1/payments?storeId=s1")
        self.assertEqual(status, 302)
        self.assertEqual(location, "http://backend-1:9001/api/v1/payments?storeId=s1")

    def test_round_robins_across_requests(self):
        pool = BackendPool(["http://b1", "http://b2"])
        addr = self._serve(pool)
        locations = [self._request(addr, "/x")[1] for _ in range(4)]
        self.assertEqual(locations, ["http://b1/x", "http://b2/x", "http://b1/x", "http://b2/x"])

    def test_503_when_no_healthy_backend(self):
        pool = BackendPool(["http://b1"], fail_threshold=1)
        pool.record_health("http://b1", False)
        addr = self._serve(pool)
        status, _ = self._request(addr, "/x")
        self.assertEqual(status, 503)

    def test_redirect_status_is_configurable(self):
        pool = BackendPool(["http://b1"])
        addr = self._serve(pool, redirect_status=307)
        status, _ = self._request(addr, "/x")
        self.assertEqual(status, 307)


if __name__ == "__main__":
    unittest.main()
