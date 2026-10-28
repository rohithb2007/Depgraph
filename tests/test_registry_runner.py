import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from depgraph.registry import Registry
from depgraph.runner import VenvRunner, execute


class RegistryTests(unittest.TestCase):
    def test_candidate_selection_excludes_prerelease_yanked_incompatible_and_major(self):
        file = {"requires_python": ">=3.11", "yanked": False}
        data = {
            "releases": {
                "1.0.0": [file],
                "1.2.0": [file],
                "1.3.0rc1": [file],
                "1.4.0": [{**file, "yanked": True}],
                "1.5.0": [{**file, "requires_python": ">=99"}],
                "2.0.0": [file],
                "99.0.0": [],
                "invalid": [file],
            }
        }
        with patch("depgraph.registry.request_json", return_value=data):
            self.assertEqual(Registry().latest("package", "1.0.0"), "1.2.0")
            self.assertEqual(Registry().latest("package", "1.0.0", True), "2.0.0")

    def test_registry_never_downgrades(self):
        with patch("depgraph.registry.request_json", return_value={"releases": {}}):
            self.assertEqual(Registry().latest("package", "3.0.0"), "3.0.0")

    def test_osv_outage_is_unknown(self):
        with patch("depgraph.registry.request_json", side_effect=OSError("offline")):
            self.assertEqual(Registry().security("x", "1")["status"], "unknown")

    def test_osv_filters_withdrawn_advisories(self):
        with patch(
            "depgraph.registry.request_json",
            return_value={"vulns": [{"id": "A", "withdrawn": "2020"}, {"id": "B"}]},
        ):
            self.assertEqual(Registry().security("x", "1")["ids"], ["B"])


class RunnerTests(unittest.TestCase):
    def test_real_command_captures_output_and_return_code(self):
        with tempfile.TemporaryDirectory() as folder:
            result = execute([sys.executable, "-c", "print('evidence'); raise SystemExit(3)"], folder)
        self.assertEqual(result["return_code"], 3)
        self.assertIn("evidence", result["stdout"])

    def test_real_timeout_is_bounded(self):
        with tempfile.TemporaryDirectory() as folder:
            result = execute([sys.executable, "-c", "import time; time.sleep(30)"], folder, timeout=0.2)
        self.assertTrue(result["timed_out"])
        self.assertNotEqual(result["return_code"], 0)

    def test_install_failure_stops_before_test_command(self):
        result = {"return_code": 0, "stdout": "", "stderr": "", "timed_out": False}
        with (
            tempfile.TemporaryDirectory() as folder,
            patch(
                "depgraph.runner.execute", side_effect=[dict(result), {**result, "return_code": 1}]
            ) as command,
        ):
            validation = VenvRunner().validate(Path(folder))
        self.assertFalse(validation["passed"])
        self.assertEqual(validation["stage"], "install")
        self.assertEqual(command.call_count, 2)


if __name__ == "__main__":
    unittest.main()
