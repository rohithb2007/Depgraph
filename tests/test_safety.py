import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from depgraph.repair import GeminiRepair
from depgraph.safety import execution_environment, private_path, redact, secret_findings


class SafetyTests(unittest.TestCase):
    def test_known_secret_detection_and_redaction_never_echo_value(self):
        value = "gh" + "p_" + "a" * 36
        text = "debug: " + value
        self.assertTrue(secret_findings(text))
        self.assertNotIn(value, redact(text))

    def test_documented_placeholders_are_allowed(self):
        self.assertEqual(secret_findings('GEMINI_API_KEY="your-gemini-api-key-here"'), [])

    def test_assigned_password_and_credential_url_are_detected(self):
        text = 'password="' + "synthetic-credential" + '"'
        self.assertTrue(secret_findings(text))
        self.assertTrue(secret_findings("postgres://account:" + "synthetic-value" + "@localhost/db"))

    def test_private_paths_cover_environment_variants_and_provider_directories(self):
        for path in [
            ".env",
            ".env.production",
            "project.env",
            ".ssh/id_rsa",
            ".aws/credentials",
            "service-account.json",
            "signing.pem",
            ".npmrc",
        ]:
            with self.subTest(path=path):
                self.assertTrue(private_path(path))
        self.assertFalse(private_path(".env.example", allow_template=True))
        self.assertFalse(private_path("app.py"))

    def test_environment_is_allowlisted_and_disables_pip_user_configuration(self):
        with patch.dict(
            os.environ,
            {
                "MY_UNUSUAL_CREDENTIAL": "not-a-real-secret",
                "GEMINI_API_KEY": "test",
                "AWS_SESSION_TOKEN": "test",
                "PATH": "tool-path",
                "PYTHONPATH": "evil",
            },
            clear=True,
        ):
            env = execution_environment()
        self.assertEqual(env["PATH"], "tool-path")
        for key in ["MY_UNUSUAL_CREDENTIAL", "GEMINI_API_KEY", "AWS_SESSION_TOKEN", "PYTHONPATH"]:
            self.assertNotIn(key, env)
        self.assertEqual(env["PIP_CONFIG_FILE"], os.devnull)

    def test_ai_is_disabled_even_if_key_and_model_exist_without_explicit_opt_in(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "synthetic", "DEPGRAPH_MODEL": "test"}, clear=True):
            self.assertIsNone(GeminiRepair().propose("x", "1", "2", "x=1", "error"))

    def test_ai_refuses_source_containing_potential_credentials_before_provider_import(self):
        source = 'credential = "' + "gh" + "p_" + "a" * 36 + '"'
        with patch.dict(os.environ, {"DEPGRAPH_ENABLE_AI": "1", "GEMINI_API_KEY": "synthetic"}, clear=True):
            with self.assertRaisesRegex(ValueError, "potential credential"):
                GeminiRepair().propose("x", "1", "2", source, "error")

    def test_staged_scanner_blocks_leaks_without_displaying_them(self):
        scanner = Path(__file__).resolve().parents[1] / "scripts/scan_secrets.py"
        with tempfile.TemporaryDirectory() as folder:
            subprocess.run(["git", "init", "-q", folder], check=True, capture_output=True)
            value = "gh" + "p_" + "b" * 36
            Path(folder, "app.py").write_text('key = "' + value + '"', encoding="utf-8")
            subprocess.run(["git", "-C", folder, "add", "app.py"], check=True, capture_output=True)
            result = subprocess.run(
                [sys.executable, str(scanner)], cwd=folder, capture_output=True, text=True, check=False
            )
        self.assertEqual(result.returncode, 1)
        self.assertIn("BLOCKED", result.stdout)
        self.assertNotIn(value, result.stdout + result.stderr)
