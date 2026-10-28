import json
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from depgraph.server import Workbench
from depgraph.store import Store


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / "runs")
        self.server = Workbench(("127.0.0.1", 0), self.store)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.temp.cleanup()

    def request(self, path, body=None, token=True, origin=None):
        headers = {}
        if token:
            headers["X-DepGraph-Token"] = self.server.token
        if origin:
            headers["Origin"] = origin
        req = urllib.request.Request(
            self.base + path, data=json.dumps(body).encode() if body is not None else None, headers=headers
        )
        # Ignore host proxy configuration for these loopback tests.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(req, timeout=5) as response:
                data = response.read().decode()
                return response.status, json.loads(data) if "application/json" in response.headers[
                    "Content-Type"
                ] else data
        except urllib.error.HTTPError as exc:
            return exc.code, json.load(exc)

    def test_health_and_static_assets(self):
        self.assertEqual(self.request("/health")[0], 200)
        for path in ["/", "/app.js", "/style.css"]:
            self.assertEqual(self.request(path)[0], 200)

    def test_get_cannot_start_mutating_workflow(self):
        self.assertEqual(self.request("/api/demo")[0], 404)
        self.assertEqual(self.store.list(), [])

    def test_post_requires_session_token(self):
        self.assertEqual(self.request("/api/demo", {}, token=False)[0], 403)

    def test_cross_origin_post_is_rejected(self):
        self.assertEqual(self.request("/api/demo", {}, origin="https://attacker.example")[0], 403)

    def test_fetch_metadata_rejects_cross_site_config_reads(self):
        req = urllib.request.Request(self.base + "/api/config", headers={"Sec-Fetch-Site": "cross-site"})
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with self.assertRaises(urllib.error.HTTPError) as error:
            opener.open(req, timeout=5)
        self.assertEqual(error.exception.code, 403)

    def test_responses_have_privacy_and_embedding_restrictions(self):
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(self.base + "/health", timeout=5) as response:
            self.assertEqual(response.headers["Referrer-Policy"], "no-referrer")
            self.assertEqual(response.headers["Cross-Origin-Resource-Policy"], "same-origin")
            self.assertIn("object-src 'none'", response.headers["Content-Security-Policy"])

    def test_real_analysis_requires_explicit_trusted_repo(self):
        status, data = self.request("/api/analyze", {})
        self.assertEqual(status, 400)
        self.assertIn("--trust-repo", data["error"])
        self.assertFalse(self.server.busy.locked())

    def test_conflicting_job_is_rejected(self):
        self.server.busy.acquire()
        try:
            self.assertEqual(self.request("/api/demo", {})[0], 409)
        finally:
            self.server.busy.release()

    def test_async_demo_records_and_exports_real_test_evidence(self):
        status, data = self.request("/api/demo", {})
        self.assertEqual(status, 202)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            status, run = self.request("/api/runs/" + data["id"])
            if run["status"] not in {"queued", "running"}:
                break
            time.sleep(0.05)
        self.assertEqual(run["status"], "ready")
        self.assertEqual(len(run["changes"]), 2)
        self.assertEqual(self.request("/api/runs/" + run["id"] + "/apply", {})[0], 400)

    def test_traversal_invalid_id_and_unknown_routes(self):
        self.assertEqual(self.request("/api/runs/not-an-id")[0], 404)
        self.assertEqual(self.request("/../../pyproject.toml")[0], 404)
        self.assertEqual(self.request("/unknown", {})[0], 404)

    def test_malformed_json_object_is_rejected(self):
        self.assertEqual(self.request("/api/demo", [1, 2])[0], 400)


if __name__ == "__main__":
    unittest.main()
