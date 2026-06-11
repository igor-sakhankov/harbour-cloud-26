import sys
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
from http.server import HTTPServer
import urllib.request
import urllib.error

sys.path.insert(0, str(Path(__file__).parent))
import load_balancer
from load_balancer import RoundRobinBalancer, is_healthy, load_config, LoadBalancerHandler


# Health check tests
class TestIsHealthy(unittest.TestCase):

    @patch("urllib.request.urlopen")
    def test_healthy_when_server_returns_200(self, mock_urlopen):
        resp = MagicMock()
        resp.status = 200
        resp.__enter__ = lambda s: s
        resp.__exit__  = MagicMock(return_value=False)
        mock_urlopen.return_value = resp
        self.assertTrue(is_healthy("http://localhost:8080"))

    @patch("urllib.request.urlopen")
    def test_healthy_when_server_returns_400(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url=None, code=400, msg="Bad Request", hdrs=None, fp=None
        )
        self.assertTrue(is_healthy("http://localhost:8080"))

    @patch("urllib.request.urlopen")
    def test_unhealthy_when_server_returns_500(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url=None, code=500, msg="Server Error", hdrs=None, fp=None
        )
        self.assertFalse(is_healthy("http://localhost:8080"))

    @patch("urllib.request.urlopen")
    def test_unhealthy_when_connection_refused(self, mock_urlopen):
        mock_urlopen.side_effect = ConnectionRefusedError()
        self.assertFalse(is_healthy("http://localhost:9999"))

    @patch("urllib.request.urlopen")
    def test_unhealthy_on_timeout(self, mock_urlopen):
        import socket
        mock_urlopen.side_effect = socket.timeout()
        self.assertFalse(is_healthy("http://localhost:8080"))


# Round-robin tests 

class TestRoundRobinBalancer(unittest.TestCase):

    def _balancer_all_healthy(self, servers):
        with patch("load_balancer.is_healthy", return_value=True):
            b = RoundRobinBalancer(servers)
            return b

    def test_cycles_through_all_servers(self):
        servers = ["http://a:8080", "http://b:8080", "http://c:8080"]
        with patch("load_balancer.is_healthy", return_value=True):
            b = RoundRobinBalancer(servers)
            results = [b.next_healthy() for _ in range(6)]
        self.assertEqual(results, [
            "http://a:8080", "http://b:8080", "http://c:8080",
            "http://a:8080", "http://b:8080", "http://c:8080",
        ])

    def test_skips_unhealthy_server(self):
        servers = ["http://dead:8080", "http://alive:8080"]
        def fake_health(url):
            return "alive" in url
        with patch("load_balancer.is_healthy", side_effect=fake_health):
            b = RoundRobinBalancer(servers)
            result = b.next_healthy()
        self.assertEqual(result, "http://alive:8080")

    def test_returns_none_when_all_down(self):
        servers = ["http://a:8080", "http://b:8080"]
        with patch("load_balancer.is_healthy", return_value=False):
            b = RoundRobinBalancer(servers)
            result = b.next_healthy()
        self.assertIsNone(result)

    def test_single_server_always_returned(self):
        servers = ["http://only:8080"]
        with patch("load_balancer.is_healthy", return_value=True):
            b = RoundRobinBalancer(servers)
            for _ in range(3):
                self.assertEqual(b.next_healthy(), "http://only:8080")


# Config loading tests 

class TestLoadConfig(unittest.TestCase):

    def test_loads_servers_from_json(self):
        config = {"servers": ["http://a:8080", "http://b:8080"]}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config, f)
            path = f.name
        servers = load_config(path)
        self.assertEqual(servers, ["http://a:8080", "http://b:8080"])

    def test_raises_on_empty_servers(self):
        config = {"servers": []}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config, f)
            path = f.name
        with self.assertRaises(ValueError):
            load_config(path)


# HTTP redirect tests 

class TestLoadBalancerHTTP(unittest.TestCase):

    def setUp(self):
        self.health_patcher = patch("load_balancer.is_healthy", return_value=True)
        self.health_patcher.start()

        LoadBalancerHandler.balancer = RoundRobinBalancer(["http://localhost:8080"])
        self.server = HTTPServer(("localhost", 0), LoadBalancerHandler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.daemon = True
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.health_patcher.stop()

    def _get_no_follow(self, path):
        import http.client
        conn = http.client.HTTPConnection("localhost", self.port, timeout=5)
        conn.request("GET", path)
        resp = conn.getresponse()
        status  = resp.status
        headers = dict(resp.getheaders())
        conn.close()
        return status, headers

    def test_get_returns_302(self):
        status, _ = self._get_no_follow("/api/v1/payments?storeId=test")
        self.assertEqual(status, 302)

    def test_location_header_points_to_backend(self):
        _, headers = self._get_no_follow("/api/v1/payments?storeId=test")
        location = headers.get("Location", "")
        self.assertIn("localhost:8080", location)

    def test_original_path_preserved_in_redirect(self):
        _, headers = self._get_no_follow("/api/v1/payments/some-id")
        location = headers.get("Location", "")
        self.assertIn("/api/v1/payments/some-id", location)

    def test_503_when_all_backends_down(self):
        with patch("load_balancer.is_healthy", return_value=False):
            LoadBalancerHandler.balancer = RoundRobinBalancer(["http://localhost:8080"])
            status, _ = self._get_no_follow("/api/v1/payments?storeId=test")
        self.assertEqual(status, 503)


if __name__ == "__main__":
    unittest.main()
