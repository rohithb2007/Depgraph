import sys
import os
import unittest
import json
from unittest.mock import patch
import tempfile
import io

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import agent

class FakeDep:
    def __init__(self, name, pinned_version, latest_version):
        self.name = name
        self.pinned_version = pinned_version
        self.latest_version = latest_version
        self.is_outdated = True

class FakeTestResult:
    def __init__(self, stage, passed):
        self.stage = stage
        self.passed = passed
        self.return_code = 0 if passed else 1
        self.stdout = ""
        self.stderr = ""

class FakeDiagnosis:
    def __init__(self, root_cause="cause", find="find", replace="replace", confidence="high", source="model", model="gemini"):
        self.root_cause = root_cause
        self.find = find
        self.replace = replace
        self.confidence = confidence
        self.source = source
        self.model = model

class FakeSecurityAssessment:
    def __init__(self, status="UNKNOWN", vulnerabilities=None, fixed_versions=None):
        self.status = status
        self.vulnerabilities = vulnerabilities or []
        self.fixed_versions = fixed_versions or []

class TestAgentIntegration(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repo_path = self.temp_dir.name
        
        self.req_path = os.path.join(self.repo_path, "requirements.txt")
        self.app_path = os.path.join(self.repo_path, "app.py")
        self.log_path = os.path.join(self.repo_path, "depgraph_run_log.json")
        
        with open(self.req_path, "w") as f: f.write("req base")
        with open(self.app_path, "w") as f: f.write("app base")
        
        self.patcher_scan = patch("agent.scan_deps")
        self.mock_scan = self.patcher_scan.start()
        self.mock_scan.return_value = [FakeDep("pkg1", "1.0.0", "2.0.0")]
        
        self.patcher_bump = patch("agent.bump_dependency")
        self.mock_bump = self.patcher_bump.start()
        def side_effect_bump(path, pkg, ver):
            with open(path, "a") as f: f.write(f"\\nbumped {pkg} to {ver}")
        self.mock_bump.side_effect = side_effect_bump
        
        self.patcher_run_tests = patch("agent.run_tests")
        self.mock_run_tests = self.patcher_run_tests.start()
        
        self.patcher_find = patch("agent.find_likely_source_file")
        self.mock_find = self.patcher_find.start()
        self.mock_find.return_value = self.app_path
        
        self.patcher_diagnose = patch("agent.diagnose_and_patch")
        self.mock_diagnose = self.patcher_diagnose.start()
        
        self.patcher_apply = patch("agent.apply_patch")
        self.mock_apply = self.patcher_apply.start()
        def side_effect_apply(path, find, replace):
            with open(path, "a") as f: f.write(f"\\napplied patch")
            return True
        self.mock_apply.side_effect = side_effect_apply
        
        self.patcher_security = patch("agent.assess_security")
        self.mock_security = self.patcher_security.start()
        self.mock_security.return_value = FakeSecurityAssessment(status="UNKNOWN")
        
    def tearDown(self):
        patch.stopall()
        self.temp_dir.cleanup()

    def get_req(self):
        with open(self.req_path, "r") as f: return f.read()
    
    def get_app(self):
        with open(self.app_path, "r") as f: return f.read()

    def get_log(self):
        if not os.path.exists(self.log_path): return {}
        with open(self.log_path, "r") as f: return json.load(f)

    @patch('sys.stdout', new_callable=io.StringIO)
    def test_1_clean_dependency_upgrade_risk_recorded(self, mock_stdout):
        self.mock_run_tests.return_value = FakeTestResult("test", True)
        agent.run_depgraph(self.repo_path)
        
        self.assertIn("bumped pkg1 to 2.0.0", self.get_req())
        self.assertEqual(self.get_app(), "app base")
        
        output = mock_stdout.getvalue()
        self.assertIn("Risk:", output)
        self.assertIn("/100 —", output)
        self.assertIn("major version change", output)
        
        log = self.get_log()
        dep = log["deps"][0]
        self.assertIn("risk", dep)
        # 40 (major) + 10 (unknown security) = 50 (MEDIUM)
        self.assertEqual(dep["risk"]["score"], 50)
        self.assertEqual(dep["risk"]["level"], "MEDIUM")
        self.assertIn("major version change", dep["risk"]["reasons"])

    @patch('sys.stdout', new_callable=io.StringIO)
    def test_2_installation_failure_risk_update(self, mock_stdout):
        self.mock_run_tests.return_value = FakeTestResult("install", False)
        agent.run_depgraph(self.repo_path)
        
        self.assertEqual(self.get_req(), "req base")
        
        log = self.get_log()
        dep = log["deps"][0]
        # 40 (major) + 50 (install fail) + 10 (unknown) = 100 (CRITICAL)
        self.assertEqual(dep["risk"]["score"], 100)
        self.assertEqual(dep["risk"]["level"], "CRITICAL")
        self.assertIn("installation failed", dep["risk"]["reasons"])

    @patch('sys.stdout', new_callable=io.StringIO)
    def test_3_test_failure_risk_update_then_repair(self, mock_stdout):
        self.mock_run_tests.side_effect = [FakeTestResult("test", False), FakeTestResult("test", True)]
        self.mock_diagnose.return_value = FakeDiagnosis()
        
        agent.run_depgraph(self.repo_path)
        
        self.assertIn("bumped pkg1 to 2.0.0", self.get_req())
        self.assertIn("applied patch", self.get_app())
        
        log = self.get_log()
        dep = log["deps"][0]
        # 40 (major) + 50 (test fail) + 10 (unknown) = 100 (CRITICAL)
        self.assertEqual(dep["risk"]["score"], 100)
        self.assertIn("test regression detected", dep["risk"]["reasons"])

    @patch('sys.stdout', new_callable=io.StringIO)
    def test_4_unsafe_gemini_patch(self, mock_stdout):
        self.mock_run_tests.return_value = FakeTestResult("test", False)
        self.mock_diagnose.return_value = FakeDiagnosis(root_cause="Gemini produced a response that failed DepGraph safety validation:", find="")
        
        agent.run_depgraph(self.repo_path)
        self.assertEqual(self.get_req(), "req base")
        
        log = self.get_log()
        dep = log["deps"][0]
        self.assertEqual(dep["risk"]["score"], 100)

    @patch('sys.stdout', new_callable=io.StringIO)
    def test_5_multiple_failed_gemini_patches(self, mock_stdout):
        self.mock_run_tests.return_value = FakeTestResult("test", False)
        self.mock_diagnose.return_value = FakeDiagnosis()
        
        agent.run_depgraph(self.repo_path)
        self.assertEqual(self.get_req(), "req base")
        
        log = self.get_log()
        dep = log["deps"][0]
        self.assertEqual(dep["risk"]["score"], 100)

    @patch('sys.stdout', new_callable=io.StringIO)
    def test_6_unexpected_exception(self, mock_stdout):
        self.mock_run_tests.side_effect = RuntimeError("random crash")
        with self.assertRaises(RuntimeError):
            agent.run_depgraph(self.repo_path)
        self.assertEqual(self.get_req(), "req base")

    @patch('sys.stdout', new_callable=io.StringIO)
    def test_7_independent_transactions(self, mock_stdout):
        self.mock_scan.return_value = [FakeDep("pkg1", "1.0", "2.0"), FakeDep("pkg2", "1.0", "2.0")]
        
        def run_tests_side_effect(*args):
            if run_tests_side_effect.calls == 0:
                res = FakeTestResult("test", True)
            else:
                res = FakeTestResult("install", False)
            run_tests_side_effect.calls += 1
            return res
        run_tests_side_effect.calls = 0
        self.mock_run_tests.side_effect = run_tests_side_effect
        
        agent.run_depgraph(self.repo_path)
        
        req = self.get_req()
        self.assertIn("bumped pkg1 to 2.0", req)
        self.assertNotIn("bumped pkg2 to 2.0", req)

if __name__ == '__main__':
    unittest.main()
