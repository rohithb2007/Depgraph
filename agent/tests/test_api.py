import os
import sys
import json
import unittest
from unittest.mock import patch, MagicMock
from http.server import HTTPServer
import threading
import urllib.request
import urllib.error

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from api import DepGraphRequestHandler


class TestAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), DepGraphRequestHandler)
        cls.port = cls.server.server_port
        cls.thread = threading.Thread(target=cls.server.serve_forever)
        cls.thread.daemon = True
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_health_endpoint(self):
        url = f"{self.base_url}/health"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data["status"], "healthy")
            self.assertEqual(data["service"], "depgraph-agent")

    @patch("api.generate_report_from_file")
    @patch("api.run_depgraph")
    def test_run_endpoint(self, mock_run_depgraph, mock_generate_report):
        mock_run_depgraph.return_value = {
            "deps": [{"name": "numpy", "outcome": "upgraded_and_fixed"}]
        }
        url = f"{self.base_url}/run"
        req = urllib.request.Request(url, method="POST")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data["status"], "success")
            self.assertEqual(data["run_summary"]["deps_analyzed"], 1)
            mock_run_depgraph.assert_called_once()
            mock_generate_report.assert_called_once()

    def test_unknown_endpoint(self):
        url = f"{self.base_url}/nonexistent"
        req = urllib.request.Request(url)
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req)
        self.assertEqual(ctx.exception.code, 404)

    def test_report_endpoint(self):
        url = f"{self.base_url}/report"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            self.assertIn("text/html", resp.headers.get("Content-Type", ""))


if __name__ == "__main__":
    unittest.main()
