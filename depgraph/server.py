"""Loopback-only workbench with persistent jobs and origin-checked mutations."""

import json
import os
import secrets
import socket
import threading
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from .demo import create_demo
from .engine import Engine
from .store import now


class Workbench(ThreadingHTTPServer):
    daemon_threads = True

    def server_bind(self):
        if os.name == "nt":
            self.allow_reuse_address = False
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()

    def __init__(self, address, store, repo=None):
        super().__init__(address, Handler)
        self.store, self.repo = store, Path(repo).resolve() if repo else None
        self.token = secrets.token_urlsafe(32)
        self.pool = ThreadPoolExecutor(max_workers=1)
        self.busy = threading.Lock()
        # A crash cannot silently turn an unfinished run into a validated one.
        for run in store.list():
            if run["status"] in {"queued", "running", "applying"}:
                run["status"] = "interrupted"
                run["finished_at"] = now()
                store.event(run, "interrupted", "Previous process stopped; inspect evidence and rerun")

    def server_close(self):
        super().server_close()
        if hasattr(self, "pool"):
            self.pool.shutdown(wait=True)


class Handler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def send(self, status, value, content_type="application/json"):
        body = json.dumps(value).encode() if content_type == "application/json" else value.encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type + "; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; style-src 'self'; script-src 'self'; "
            "connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; "
            "base-uri 'none'; form-action 'self'; object-src 'none'",
        )
        self.end_headers()
        self.wfile.write(body)

    def valid_host(self):
        return self.headers.get("Host") in {
            f"127.0.0.1:{self.server.server_port}",
            f"localhost:{self.server.server_port}",
        }

    def do_GET(self):
        if not self.valid_host() or self.headers.get("Sec-Fetch-Site") == "cross-site":
            return self.send(403, {"error": "Local host required"})
        path = urlsplit(self.path).path
        try:
            if path == "/health":
                return self.send(200, {"status": "healthy", "version": "0.2.0"})
            if path == "/api/config":
                return self.send(
                    200,
                    {
                        "token": self.server.token,
                        "repo": str(self.server.repo) if self.server.repo else None,
                        "busy": self.server.busy.locked(),
                    },
                )
            if path == "/api/runs":
                return self.send(
                    200,
                    [
                        {k: r.get(k) for k in ("id", "repo", "created_at", "status", "demo")}
                        for r in self.server.store.list()
                    ],
                )
            if path.startswith("/api/runs/"):
                return self.send(200, self.server.store.get(path.rsplit("/", 1)[1]))
            files = {
                "/": ("index.html", "text/html"),
                "/app.js": ("app.js", "text/javascript"),
                "/style.css": ("style.css", "text/css"),
            }
            if path in files:
                name, content_type = files[path]
                return self.send(
                    200, (Path(__file__).parent / "static" / name).read_text(encoding="utf-8"), content_type
                )
            self.send(404, {"error": "Not found"})
        except (ValueError, FileNotFoundError):
            self.send(404, {"error": "Run not found"})

    def do_POST(self):
        origin = self.headers.get("Origin")
        expected = {
            f"http://127.0.0.1:{self.server.server_port}",
            f"http://localhost:{self.server.server_port}",
        }
        if (
            not self.valid_host()
            or self.headers.get("Sec-Fetch-Site") == "cross-site"
            or (origin and origin not in expected)
            or not secrets.compare_digest(self.headers.get("X-DepGraph-Token", ""), self.server.token)
        ):
            return self.send(403, {"error": "Local session token and same origin required"})
        if self.headers.get("Transfer-Encoding") or not self.headers.get("Content-Length", "0").isdigit():
            return self.send(400, {"error": "Invalid request length"})
        length = int(self.headers.get("Content-Length", 0))
        if length > 4096:
            return self.send(413, {"error": "Request too large"})
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(body, dict):
                raise ValueError("Expected JSON object")
            path = urlsplit(self.path).path
            if path not in {"/api/demo", "/api/analyze"} and not (
                path.startswith("/api/runs/") and path.endswith("/apply")
            ):
                return self.send(404, {"error": "Not found"})
            if not self.server.busy.acquire(blocking=False):
                return self.send(409, {"error": "A maintenance operation is already running"})
            submitted = False
            try:
                if path.endswith("/apply"):
                    run = Engine(self.server.store).apply(path.split("/")[3])
                    return self.send(200, run)
                if path == "/api/demo":
                    engine, run = create_demo(self.server.store)
                else:
                    if not self.server.repo:
                        raise ValueError("Start server with --repo PATH --trust-repo to enable real analysis")
                    for key in ("allow_major", "allow_unknown_security"):
                        if key in body and not isinstance(body[key], bool):
                            raise ValueError(f"{key} must be boolean")
                    engine = Engine(self.server.store)
                    run = engine.create(
                        self.server.repo,
                        allow_major=body.get("allow_major", False),
                        allow_unknown=body.get("allow_unknown_security", False),
                    )
                self.server.pool.submit(self.execute_run, engine, run)
                submitted = True
                self.send(202, {"id": run["id"]})
            finally:
                if not submitted:
                    self.server.busy.release()
        except (ValueError, FileNotFoundError, IndexError) as exc:
            self.send(400, {"error": str(exc)})

    def execute_run(self, engine, run):
        try:
            engine.run(run)
        finally:
            self.server.busy.release()

    def log_message(self, message, *args):
        pass


def serve(store, port=8080, repo=None):
    with Workbench(("127.0.0.1", port), store, repo) as server:
        print(f"DepGraph workbench: http://127.0.0.1:{server.server_port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
