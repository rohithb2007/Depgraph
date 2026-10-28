import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from depgraph.demo import APP, TESTS, DemoRegistry, DemoRepair, DemoRunner, create_demo
from depgraph.engine import Engine
from depgraph.project import bump, graph, inventory, manifest
from depgraph.repair import checked_patch
from depgraph.store import Store, digest, verify_events


class ProjectCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "project"
        self.repo.mkdir()
        (self.repo / "tests").mkdir()
        (self.repo / "app.py").write_text(APP, encoding="utf-8")
        (self.repo / "tests/test_contract.py").write_text(TESTS, encoding="utf-8")
        (self.repo / "requirements.txt").write_text(
            "responsekit==1.0.0\nformatkit==1.0.0\nguardkit==1.0.0\n", encoding="utf-8"
        )
        self.store = Store(self.root / "runs")
        self.engine = Engine(self.store, DemoRegistry(), DemoRunner(), DemoRepair())

    def run_fixture(self, **policy):
        return self.engine.run(self.engine.create(self.repo, allow_major=True, **policy))


class EngineTests(ProjectCase):
    def test_real_subprocess_clean_repair_rollback_and_unchanged_source(self):
        before = inventory(self.repo)
        run = self.run_fixture()
        self.assertEqual(run["status"], "ready")
        self.assertEqual([c["outcome"] for c in run["candidates"]], ["repaired", "upgraded", "rolled_back"])
        self.assertEqual(inventory(self.repo), before)
        changes = {c["path"]: c for c in run["changes"]}
        self.assertIn("responsekit==2.0.0", changes["requirements.txt"]["after"])
        self.assertIn("guardkit==1.0.0", changes["requirements.txt"]["after"])
        self.assertIn("return float(", changes["app.py"]["after"])
        self.assertTrue(verify_events(run["events"]))
        self.assertIn("Ran 4 tests", run["baseline"]["commands"][0]["stderr"])
        self.assertEqual(self.store.get(run["id"])["patch_hash"], digest(run["changes"]))

    def test_reviewed_patch_applies_and_cannot_apply_twice(self):
        run = self.run_fixture()
        result = self.engine.apply(run["id"])
        self.assertEqual(result["status"], "applied")
        self.assertIn("responsekit==2.0.0", (self.repo / "requirements.txt").read_text())
        self.assertTrue(verify_events(result["events"]))
        with self.assertRaisesRegex(ValueError, "not ready"):
            self.engine.apply(run["id"])

    def test_stale_source_prevents_apply_without_overwriting_user_changes(self):
        run = self.run_fixture()
        (self.repo / "app.py").write_text("# new user work\n")
        before = inventory(self.repo)
        with self.assertRaisesRegex(ValueError, "changed since"):
            self.engine.apply(run["id"])
        self.assertEqual(inventory(self.repo), before)

    def test_demo_cannot_apply(self):
        engine, run = create_demo(self.store)
        engine.run(run)
        with self.assertRaisesRegex(ValueError, "Demo patches"):
            engine.apply(run["id"])

    def test_patch_tampering_rejected(self):
        run = self.run_fixture()
        run["changes"][0]["after"] += "# changed\n"
        self.store.save(run)
        with self.assertRaisesRegex(ValueError, "Patch integrity"):
            self.engine.apply(run["id"])

    def test_apply_failure_restores_all_files(self):
        run = self.run_fixture()
        before = inventory(self.repo)
        import depgraph.engine as module

        original = module.os.replace

        def fail_second(src, dst):
            if Path(dst) == self.repo / "requirements.txt":
                raise OSError("injected disk failure")
            return original(src, dst)

        with patch("depgraph.engine.os.replace", side_effect=fail_second):
            with self.assertRaises(OSError):
                self.engine.apply(run["id"])
        self.assertEqual(inventory(self.repo), before)
        self.assertEqual(self.store.get(run["id"])["status"], "ready")
        self.assertFalse((self.repo / ".depgraph/apply.lock").exists())

    def test_baseline_failure_blocks_all_upgrades(self):
        with patch.object(
            self.engine.runner, "validate", return_value={"passed": False, "stage": "test", "commands": []}
        ):
            run = self.run_fixture()
        self.assertEqual(run["status"], "baseline_failed")
        self.assertEqual(run["candidates"], [])
        self.assertIn("finished_at", self.store.get(run["id"]))

    def test_unknown_security_blocks_by_default(self):
        with patch.object(self.engine.registry, "security", return_value={"status": "unknown", "ids": []}):
            run = self.run_fixture()
        self.assertEqual(run["status"], "no_changes")
        self.assertTrue(all(c["outcome"] == "policy_blocked" for c in run["candidates"]))

    def test_unknown_security_requires_explicit_override(self):
        with patch.object(self.engine.registry, "security", return_value={"status": "unknown", "ids": []}):
            run = self.run_fixture(allow_unknown=True)
        self.assertEqual(run["status"], "ready")

    def test_vulnerable_candidate_cannot_be_overridden(self):
        with patch.object(
            self.engine.registry, "security", return_value={"status": "vulnerable", "ids": ["X"]}
        ):
            run = self.run_fixture(allow_unknown=True)
        self.assertEqual(run["status"], "no_changes")

    def test_install_failure_never_reaches_repair(self):
        baseline = {"passed": True, "stage": "test", "commands": []}
        failure = {"passed": False, "stage": "install", "commands": []}
        with (
            patch.object(self.engine.runner, "validate", side_effect=[baseline, failure, failure, failure]),
            patch.object(self.engine.repair, "propose") as repair,
        ):
            run = self.run_fixture()
        repair.assert_not_called()
        self.assertEqual([c["outcome"] for c in run["candidates"]], ["rolled_back"] * 3)
        self.assertFalse(run["changes"])

    def test_baseline_cannot_rewrite_tests(self):
        def malicious(work):
            (work / "tests/test_contract.py").write_text("# erased\n")
            return {"passed": True, "stage": "test", "commands": []}

        with patch.object(self.engine.runner, "validate", side_effect=malicious):
            run = self.run_fixture()
        self.assertEqual(run["status"], "failed")
        self.assertIn("modified source", run["error"])

    def test_registry_outage_is_recorded_per_package(self):
        with patch.object(self.engine.registry, "latest", side_effect=OSError("offline")):
            run = self.run_fixture()
        self.assertTrue(all(c["outcome"] == "lookup_failed" for c in run["candidates"]))

    def test_event_tampering_is_detected(self):
        run = self.run_fixture()
        run["events"][0]["message"] = "rewritten"
        self.assertFalse(verify_events(run["events"]))


class ManifestTests(ProjectCase):
    def test_extras_markers_comments_and_normalization(self):
        path = self.repo / "requirements.txt"
        path.write_text('Requests[socks]==2.0.0; python_version >= "3.0" # keep me\n')
        deps = manifest(self.repo)
        self.assertEqual(deps[0]["name"], "requests")
        bump(path, "requests", "2.1.0")
        self.assertIn('Requests[socks]==2.1.0; python_version >= "3.0" # keep me', path.read_text())

    def test_ranges_urls_includes_and_duplicates_rejected(self):
        for value in ["requests>=2", "-r other.txt", "x @ https://example.com/x.whl", "a==1\na==2"]:
            with self.subTest(value=value):
                (self.repo / "requirements.txt").write_text(value)
                with self.assertRaises(ValueError):
                    manifest(self.repo)

    def test_import_graph_ignores_virtualenv_and_test_aliases(self):
        (self.repo / ".venv").mkdir()
        (self.repo / ".venv/junk.py").write_text("import responsekit")
        result = graph(self.repo, manifest(self.repo))
        self.assertEqual(len(result["edges"]), 3)
        self.assertNotIn(".venv/junk.py", result["files"])

    def test_bump_preserves_crlf(self):
        path = self.repo / "requirements.txt"
        path.write_bytes(b"responsekit==1.0.0\r\n# comment\r\n")
        bump(path, "responsekit", "2.0.0")
        self.assertEqual(path.read_bytes(), b"responsekit==2.0.0\r\n# comment\r\n")


class RepairTests(unittest.TestCase):
    def test_patch_rejects_ambiguous_empty_noop_and_syntax_errors(self):
        for source, proposal in [
            ("x=1\nx=1", {"find": "x=1", "replace": "x=2"}),
            ("x=1", {"find": "", "replace": ""}),
            ("x=1", {"find": "x=1", "replace": "x=1"}),
            ("x=1", {"find": "x=1", "replace": "x=("}),
        ]:
            with self.subTest(proposal=proposal), self.assertRaises((ValueError, SyntaxError)):
                checked_patch(source, proposal)

    def test_assertion_removal_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "assertions"):
            checked_patch("assert value\n", {"find": "assert value", "replace": "pass"})

    def test_exception_suppression_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "exception"):
            checked_patch("x=1\n", {"find": "x=1", "replace": "try:\n x=1\nexcept:\n pass"})


if __name__ == "__main__":
    unittest.main()
