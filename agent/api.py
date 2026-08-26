"""
DepGraph HTTP API Server for Cloud Run deployment.

Provides lightweight REST endpoints around the DepGraph workflow:
- GET  /health : Health check endpoint for Cloud Run container probes
- POST /run    : Trigger DepGraph workflow on target-repo and generate HTML report
- GET  /run    : Trigger DepGraph workflow on target-repo and generate HTML report
- GET  /report : Serve generated HTML report
"""

import os
import sys
import json
from http.server import HTTPServer, BaseHTTPRequestHandler

# Ensure agent and tools are in sys.path
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "tools"))

from agent import run_depgraph
from report import generate_report_from_file


class DepGraphRequestHandler(BaseHTTPRequestHandler):
    def _send_json(self, status_code: int, data: dict):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, status_code: int, html_content: str):
        body = html_content.encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            self._send_json(200, {"status": "healthy", "service": "depgraph-agent"})
        elif self.path == "/report":
            report_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "target-repo", "depgraph_report.html"))
            if os.path.exists(report_path):
                with open(report_path, "r", encoding="utf-8") as f:
                    content = f.read()
                self._send_html(200, content)
            else:
                self._send_json(404, {"error": "Report not found. Run /run first."})
        elif self.path in ("/run", "/api/run"):
            self._handle_run()
        else:
            self._send_json(404, {"error": "Endpoint not found"})

    def do_POST(self):
        if self.path in ("/run", "/api/run"):
            self._handle_run()
        else:
            self._send_json(404, {"error": "Endpoint not found"})

    def _handle_run(self):
        try:
            target_repo = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "target-repo"))
            run_log = run_depgraph(target_repo)
            
            log_path = os.path.join(target_repo, "depgraph_run_log.json")
            report_path = os.path.join(target_repo, "depgraph_report.html")
            generate_report_from_file(log_path, report_path)
            
            self._send_json(200, {
                "status": "success",
                "message": "DepGraph workflow completed successfully.",
                "run_summary": {
                    "deps_analyzed": len(run_log.get("deps", [])),
                    "outcomes": [d.get("outcome") for d in run_log.get("deps", []) if isinstance(d, dict)]
                }
            })
        except Exception as e:
            self._send_json(500, {"status": "error", "message": str(e)})

    def log_message(self, format, *args):
        # Clean logging format
        sys.stderr.write("[api] %s - - [%s] %s\n" % (self.address_string(), self.log_date_time_string(), format % args))


def run_server(port: int = None):
    if port is None:
        port = int(os.environ.get("PORT", "8080"))
    server_address = ("", port)
    httpd = HTTPServer(server_address, DepGraphRequestHandler)
    print(f"DepGraph API server listening on 0.0.0.0:{port}...")
    httpd.serve_forever()


if __name__ == "__main__":
    run_server()
