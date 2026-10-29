import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class CliTests(unittest.TestCase):
    def test_demo_succeeds_when_console_encoding_cannot_represent_version_arrows(self):
        with tempfile.TemporaryDirectory() as folder:
            result = subprocess.run(
                [sys.executable, "-m", "depgraph", "--state", str(Path(folder) / "runs"), "demo"],
                cwd=Path(__file__).resolve().parents[1],
                env={**os.environ, "PYTHONIOENCODING": "ascii"},
                capture_output=True,
                timeout=30,
                check=False,
            )
        self.assertEqual(result.returncode, 0, result.stderr.decode("ascii", errors="replace"))
        self.assertIn(b"ready", result.stdout)
        self.assertIn(b"repaired", result.stdout)
        self.assertIn(b"rolled_back", result.stdout)
