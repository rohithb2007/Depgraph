import os
import sys
import json
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "tools")))
from report import generate_report, generate_report_from_file


class TestReport(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repo_path = self.temp_dir.name

    def tearDown(self):
        self.temp_dir.cleanup()

    def _sample_run_log(self):
        return {
            "repo": "/path/to/demo_repo",
            "started_at": 1700000000.0,
            "finished_at": 1700000060.0,
            "dependency_graph": {
                "summary": {
                    "declared_dependencies": 2,
                    "used_dependencies": 1,
                    "unused_dependencies": 1,
                    "third_party_imports": 1,
                    "unresolved_imports": 0,
                    "files_analyzed": 1,
                },
                "dependencies": [
                    {"name": "requests", "used": True},
                    {"name": "pytest", "used": False},
                ],
                "files": [
                    {
                        "file": "app.py",
                        "imports": [{"module": "requests", "dependency": "requests"}],
                    }
                ],
            },
            "deps": [
                {
                    "name": "requests",
                    "from": "2.28.0",
                    "to": "2.31.0",
                    "outcome": "upgraded_clean",
                    "security": {
                        "current": {"status": "SAFE", "vulnerabilities": []},
                        "candidate": {"status": "SAFE", "vulnerabilities": []},
                    },
                    "risk": {
                        "score": 20,
                        "level": "LOW",
                        "reasons": ["minor version change"],
                    },
                    "attempts": [],
                },
                {
                    "name": "urllib3",
                    "from": "1.26.5",
                    "to": "2.0.0",
                    "outcome": "upgraded_and_fixed",
                    "security": {
                        "current": {
                            "status": "VULNERABLE",
                            "vulnerabilities": ["GHSA-4637-v45f-45rr"],
                        },
                        "candidate": {"status": "SAFE", "vulnerabilities": []},
                    },
                    "risk": {
                        "score": 60,
                        "level": "HIGH",
                        "reasons": ["major version change", "vulnerable pinned version"],
                    },
                    "attempts": [
                        {
                            "attempt": 1,
                            "diagnosis": "Method signature changed in v2",
                            "confidence": "high",
                            "diagnosis_source": "gemini",
                            "model": "gemini-1.5-pro",
                            "patch_find": "old_method()",
                            "patch_replace": "new_method()",
                            "patch_applied": True,
                            "result": "tests_passed",
                        }
                    ],
                },
                {
                    "name": "flask",
                    "from": "2.0.0",
                    "to": "3.0.0",
                    "outcome": "failed_rolled_back",
                    "security": {
                        "current": {"status": "SAFE", "vulnerabilities": []},
                        "candidate": {"status": "SAFE", "vulnerabilities": []},
                    },
                    "risk": {
                        "score": 100,
                        "level": "CRITICAL",
                        "reasons": ["test regression detected"],
                    },
                    "attempts": [
                        {
                            "attempt": 1,
                            "diagnosis": "Incompatible request context",
                            "confidence": "medium",
                            "diagnosis_source": "gemini",
                            "model": "gemini-1.5-pro",
                            "patch_find": "request.args",
                            "patch_replace": "request.form",
                            "patch_applied": True,
                            "result": "tests_still_failing",
                        }
                    ],
                },
            ],
        }

    def test_1_basic_successful_report_generation(self):
        run_log = self._sample_run_log()
        html_report = generate_report(run_log)
        self.assertIsInstance(html_report, str)
        self.assertIn("<!DOCTYPE HTML>", html_report.upper() if html_report else "")
        self.assertIn("/path/to/demo_repo", html_report)

    def test_2_dependency_table_rendering(self):
        run_log = self._sample_run_log()
        html_report = generate_report(run_log)
        self.assertIn("requests", html_report)
        self.assertIn("2.28.0", html_report)
        self.assertIn("2.31.0", html_report)
        self.assertIn("urllib3", html_report)
        self.assertIn("1.26.5", html_report)
        self.assertIn("2.0.0", html_report)

    def test_3_risk_and_security_rendering(self):
        run_log = self._sample_run_log()
        html_report = generate_report(run_log)
        self.assertIn("LOW", html_report)
        self.assertIn("HIGH", html_report)
        self.assertIn("CRITICAL", html_report)
        self.assertIn("GHSA-4637-v45f-45rr", html_report)
        self.assertIn("vulnerable pinned version", html_report)

    def test_4_dependency_graph_rendering(self):
        run_log = self._sample_run_log()
        html_report = generate_report(run_log)
        self.assertIn("declared_dependencies", html_report.lower() if html_report else "")
        self.assertIn("app.py", html_report)

    def test_5_gemini_diagnosis_repair_rendering(self):
        run_log = self._sample_run_log()
        html_report = generate_report(run_log)
        self.assertIn("Method signature changed in v2", html_report)
        self.assertIn("old_method()", html_report)
        self.assertIn("new_method()", html_report)
        self.assertIn("tests_passed", html_report)

    def test_6_rollback_rendering(self):
        run_log = self._sample_run_log()
        html_report = generate_report(run_log)
        self.assertIn("flask", html_report)
        self.assertIn("failed_rolled_back", html_report)

    def test_7_missing_optional_fields_degraded_run_log(self):
        minimal_log = {
            "repo": "/minimal/repo",
            "deps": [
                {
                    "name": "pytz",
                    "from": "2021.1",
                    "to": "2023.3",
                    "outcome": "upgraded_clean",
                }
            ],
        }
        html_report = generate_report(minimal_log)
        self.assertIsInstance(html_report, str)
        self.assertIn("pytz", html_report)

    def test_8_html_escaping_security(self):
        malicious_log = {
            "repo": "<script>alert('xss_repo')</script>",
            "deps": [
                {
                    "name": "<b onmouseover=alert(1)>pkg</b>",
                    "from": "1.0<script>",
                    "to": "2.0",
                    "outcome": "<b>failed</b>",
                    "risk": {
                        "score": 50,
                        "level": "MEDIUM",
                        "reasons": ["<img src=x onerror=alert(1)>"],
                    },
                    "attempts": [
                        {
                            "attempt": 1,
                            "diagnosis": "<iframe src='evil.com'></iframe>",
                            "confidence": "high",
                            "result": "failed",
                        }
                    ],
                }
            ],
        }
        html_report = generate_report(malicious_log)
        self.assertNotIn("<script>alert('xss_repo')</script>", html_report)
        self.assertNotIn("<img src=x onerror=alert(1)>", html_report)
        self.assertNotIn("<iframe src='evil.com'></iframe>", html_report)

    def test_9_empty_dependency_list(self):
        empty_log = {
            "repo": "/empty/repo",
            "started_at": 1700000000.0,
            "finished_at": 1700000010.0,
            "deps": [],
        }
        html_report = generate_report(empty_log)
        self.assertIsInstance(html_report, str)
        self.assertIn("/empty/repo", html_report)

    def test_10_output_file_creation(self):
        run_log = self._sample_run_log()

        out_path = os.path.join(self.repo_path, "report.html")
        html_content = generate_report(run_log, out_path)
        self.assertTrue(os.path.exists(out_path))
        with open(out_path, "r", encoding="utf-8") as f:
            saved_content = f.read()
        self.assertEqual(html_content, saved_content)

        json_log_path = os.path.join(self.repo_path, "depgraph_run_log.json")
        with open(json_log_path, "w", encoding="utf-8") as f:
            json.dump(run_log, f)

        out_path_2 = os.path.join(self.repo_path, "report_from_file.html")
        html_content_2 = generate_report_from_file(json_log_path, out_path_2)
        self.assertTrue(os.path.exists(out_path_2))
        with open(out_path_2, "r", encoding="utf-8") as f:
            saved_content_2 = f.read()
        self.assertEqual(html_content_2, saved_content_2)


if __name__ == "__main__":
    unittest.main()
