import unittest

from depgraph.report import render_report


class ReportTests(unittest.TestCase):
    def test_report_escapes_untrusted_repository_model_and_command_text(self):
        payload = '<script>alert("x")</script>'
        run = {
            "id": "abc",
            "repo": payload,
            "status": "ready",
            "demo": True,
            "events": [],
            "changes": [{"path": "app.py", "diff": payload}],
            "candidates": [],
            "baseline": {
                "passed": True,
                "commands": [{"command": ["python"], "return_code": 0, "stdout": payload, "stderr": ""}],
            },
        }
        report = render_report(run)
        self.assertNotIn("<script>", report)
        self.assertIn("&lt;script&gt;", report)
        self.assertIn("OFFLINE FIXTURE", report)
