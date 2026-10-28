"""Offline integration fixture. Real subprocess tests against two local API versions.

This deliberately uses local modules rather than claiming to query PyPI or OSV.
"""

import os
import sys
import tempfile
from pathlib import Path

from .engine import Engine
from .runner import execute

APP = """import responsekit
import formatkit
import guardkit


def average(samples):
    return responsekit.legacy_float(sum(samples) / len(samples))


def label(value):
    return formatkit.render(value)


def authorize():
    return guardkit.allowed()
"""
TESTS = """import unittest
from app import average, label, authorize


class ContractTests(unittest.TestCase):
    def test_average(self):
        self.assertAlmostEqual(average([1, 2, 3]), 2.0)

    def test_type(self):
        self.assertIsInstance(average([4]), float)

    def test_format(self):
        self.assertEqual(label(42), "value:42")

    def test_authorization_contract(self):
        self.assertTrue(authorize())
"""


class DemoRegistry:
    def latest(self, name, current, allow_major=False):
        return {"responsekit": "2.0.0", "formatkit": "1.1.0", "guardkit": "2.0.0"}[name]

    def security(self, name, version):
        return {"status": "clear", "ids": [], "source": "local fixture (no OSV query)"}


class DemoRepair:
    def propose(self, package, before, after, source, output):
        if package == "responsekit" and "legacy_float" in output:
            return {
                "root_cause": "responsekit 2 removed legacy_float, an alias for built-in float",
                "find": "responsekit.legacy_float(",
                "replace": "float(",
                "provider": "deterministic fixture rule",
                "model": None,
            }
        return None


class DemoRunner:
    def validate(self, repo):
        from .project import manifest

        versions = {d["name"]: d["version"] for d in manifest(repo)}
        with tempfile.TemporaryDirectory(prefix="depgraph-fixture-api-") as folder:
            modules = {
                "responsekit": "legacy_float = float\n"
                if versions["responsekit"] == "1.0.0"
                else "API_VERSION = 2\n",
                "formatkit": "def render(value):\n    return 'value:' + str(value)\n",
                "guardkit": "def allowed():\n    return " + str(versions["guardkit"] == "1.0.0") + "\n",
            }
            for name, content in modules.items():
                Path(folder, f"{name}.py").write_text(content, encoding="utf-8")
            env = {**os.environ, "PYTHONPATH": folder, "PYTHONDONTWRITEBYTECODE": "1"}
            result = execute(
                [sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests", "-v"],
                repo,
                timeout=30,
                env=env,
            )
            result["stage"] = "test"
            return {
                "passed": result["return_code"] == 0,
                "stage": "test",
                "commands": [result],
                "resolved": versions,
                "execution": "local fixture modules; real unittest subprocess",
            }


def demo_engine(store):
    return Engine(store, DemoRegistry(), DemoRunner(), DemoRepair())


def create_demo(store):
    root = store.root / "demo-project"
    root.mkdir(exist_ok=True)
    (root / "tests").mkdir(exist_ok=True)
    (root / "app.py").write_text(APP, encoding="utf-8")
    (root / "tests" / "test_contract.py").write_text(TESTS, encoding="utf-8")
    (root / "requirements.txt").write_text(
        "responsekit==1.0.0\nformatkit==1.0.0\nguardkit==1.0.0\n", encoding="utf-8"
    )
    engine = demo_engine(store)
    return engine, engine.create(root, allow_major=True, demo=True)
