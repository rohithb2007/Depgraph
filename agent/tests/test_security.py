import sys
import os
import unittest
from unittest.mock import patch, MagicMock
import urllib.error

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "tools")))
from security import assess_security

class TestSecurity(unittest.TestCase):
    @patch('urllib.request.urlopen')
    def test_1_vulnerable_package(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = b'{"vulns": [{"id": "CVE-2023-1234", "summary": "Test vul", "affected": [{"package": {"name": "test-pkg"}, "ranges": [{"type": "ECOSYSTEM", "events": [{"introduced": "0"}, {"fixed": "1.0.1"}]}]}]}]}'
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response
        
        result = assess_security("test-pkg", "1.0.0")
        self.assertEqual(result.status, "VULNERABLE")
        self.assertEqual(len(result.vulnerabilities), 1)
        self.assertEqual(result.vulnerabilities[0].id, "CVE-2023-1234")
        self.assertIn("1.0.1", result.vulnerabilities[0].fixed_versions)
        self.assertIn("1.0.1", result.fixed_versions)

    @patch('urllib.request.urlopen')
    def test_2_no_vulnerabilities(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = b'{}'
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response
        
        result = assess_security("test-pkg", "1.0.1")
        self.assertEqual(result.status, "SAFE")
        self.assertEqual(len(result.vulnerabilities), 0)

    @patch('urllib.request.urlopen')
    def test_4_osv_timeout(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.URLError("timeout")
        
        result = assess_security("test-pkg", "1.0.0")
        self.assertEqual(result.status, "UNKNOWN")
        self.assertIn("Network or parse error", result.reason)

    @patch('urllib.request.urlopen')
    def test_5_network_failure(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.status = 500
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response
        
        result = assess_security("test-pkg", "1.0.0")
        self.assertEqual(result.status, "UNKNOWN")
        self.assertIn("HTTP 500", result.reason)

    @patch('urllib.request.urlopen')
    def test_6_malformed_osv_response(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = b'not json'
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response
        
        result = assess_security("test-pkg", "1.0.0")
        self.assertEqual(result.status, "UNKNOWN")

if __name__ == '__main__':
    unittest.main()
