import sys
import os
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "tools")))
from risk import assess_risk

class TestRiskScoring(unittest.TestCase):
    def test_1_patch_level_upgrade(self):
        result = assess_risk("1.0.0", "1.0.1", candidate_security_status="SAFE")
        self.assertEqual(result.score, 5)
        self.assertEqual(result.level, "LOW")
        self.assertIn("patch version change", result.reasons)

    def test_2_minor_level_upgrade(self):
        result = assess_risk("1.0.0", "1.1.0", candidate_security_status="SAFE")
        self.assertEqual(result.score, 20)
        self.assertEqual(result.level, "LOW")
        self.assertIn("minor version change", result.reasons)

    def test_3_major_level_upgrade(self):
        result = assess_risk("1.0.0", "2.0.0", candidate_security_status="SAFE")
        self.assertEqual(result.score, 40)
        self.assertEqual(result.level, "MEDIUM")
        self.assertIn("major version change", result.reasons)

    def test_4_python_compatible_candidate(self):
        # target python is 3.11
        result = assess_risk("1.0", "1.1", requires_python=">=3.8", candidate_security_status="SAFE")
        self.assertEqual(result.score, 20) # 20 from minor jump
        self.assertNotIn("candidate incompatible with target Python 3.11", result.reasons)

    def test_5_python_incompatible_candidate(self):
        result = assess_risk("1.0", "1.1", requires_python=">=3.12", candidate_security_status="SAFE")
        self.assertEqual(result.score, 100) # Capped at 100
        self.assertEqual(result.level, "CRITICAL")
        self.assertIn("candidate incompatible with target Python 3.11", result.reasons)

    def test_6_installation_failure(self):
        result = assess_risk("1.0", "1.1", install_success=False, candidate_security_status="SAFE")
        self.assertEqual(result.score, 70) # 20 (minor) + 50 (install fail) = 70
        self.assertEqual(result.level, "HIGH")
        self.assertIn("installation failed", result.reasons)

    def test_7_test_failure(self):
        result = assess_risk("1.0", "1.0.1", test_success=False, candidate_security_status="SAFE")
        self.assertEqual(result.score, 55) # 5 (patch) + 50 (test fail) = 55
        self.assertEqual(result.level, "MEDIUM")
        self.assertIn("test regression detected", result.reasons)

    def test_8_security_unknown(self):
        result = assess_risk("1.0", "1.0.1", candidate_security_status="UNKNOWN")
        self.assertEqual(result.score, 15) # 5 (patch) + 10 (unknown) = 15
        self.assertIn("candidate security status unknown", result.reasons)

    def test_9_deterministic_identical_inputs(self):
        res1 = assess_risk("1.0", "2.0", requires_python=">=3.8", install_success=True, test_success=False, candidate_security_status="UNKNOWN", impact_files=5)
        res2 = assess_risk("1.0", "2.0", requires_python=">=3.8", install_success=True, test_success=False, candidate_security_status="UNKNOWN", impact_files=5)
        self.assertEqual(res1.score, res2.score)
        self.assertEqual(res1.level, res2.level)
        self.assertEqual(res1.reasons, res2.reasons)
        
        # 40 (major) + 0 (comp) + 0 (install) + 50 (test) + 10 (sec) + 10 (impact) = 110 -> 100
        self.assertEqual(res1.score, 100)
        self.assertEqual(res1.level, "CRITICAL")

    def test_10_score_boundary_level_mapping(self):
        # 0-29: LOW
        self.assertEqual(assess_risk("1.0", "1.0", candidate_security_status="SAFE").level, "LOW") # 0
        self.assertEqual(assess_risk("1.0", "1.1", candidate_security_status="SAFE").level, "LOW") # 20
        # 30-59: MEDIUM
        self.assertEqual(assess_risk("1.0", "2.0", candidate_security_status="SAFE").level, "MEDIUM") # 40
        # 60-79: HIGH
        self.assertEqual(assess_risk("1.0", "2.0", candidate_security_status="SAFE", impact_files=10).level, "HIGH") # 40 + 20 = 60
        # 80-100: CRITICAL
        self.assertEqual(assess_risk("1.0", "2.0", candidate_security_status="UNKNOWN", test_success=False).level, "CRITICAL") # 40 + 10 + 50 = 100 (capped)

    def test_11_vulnerable_pinned_resolved(self):
        result = assess_risk("1.0", "2.0", current_security_status="VULNERABLE", candidate_security_status="SAFE")
        # 40 (major) + 15 (pinned vuln) - 15 (resolved) = 40
        self.assertEqual(result.score, 40)
        self.assertIn("candidate resolves pinned vulnerabilities (positive security evidence)", result.reasons)

    def test_12_vulnerable_candidate(self):
        result = assess_risk("1.0", "2.0", candidate_security_status="VULNERABLE")
        self.assertEqual(result.score, 100)
        self.assertIn("candidate has known security vulnerabilities", result.reasons)

if __name__ == '__main__':
    unittest.main()
