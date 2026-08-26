import os
import sys
import json
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'tools')))
from graph import build_dependency_graph

class TestGraph(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repo_path = self.temp_dir.name
        self.req_path = os.path.join(self.repo_path, "requirements.txt")
        
    def tearDown(self):
        self.temp_dir.cleanup()
        
    def write_file(self, filename, content):
        path = os.path.join(self.repo_path, filename)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
            
    def test_import_numpy(self):
        self.write_file("requirements.txt", "numpy==1.23.5\n")
        self.write_file("app.py", "import numpy\n")
        
        graph = build_dependency_graph(self.repo_path, self.req_path)
        
        self.assertEqual(graph["summary"]["used_dependencies"], 1)
        self.assertEqual(graph["summary"]["unresolved_imports"], 0)
        self.assertEqual(graph["dependencies"][0]["name"], "numpy")
        self.assertTrue(graph["dependencies"][0]["used"])
        self.assertEqual(graph["files"][0]["imports"][0]["module"], "numpy")
        self.assertEqual(graph["files"][0]["imports"][0]["dependency"], "numpy")

    def test_import_numpy_as_np(self):
        self.write_file("requirements.txt", "numpy==1.23.5\n")
        self.write_file("app.py", "import numpy as np\n")
        
        graph = build_dependency_graph(self.repo_path, self.req_path)
        self.assertTrue(graph["dependencies"][0]["used"])
        self.assertEqual(graph["files"][0]["imports"][0]["module"], "numpy")

    def test_from_requests_import_get(self):
        self.write_file("requirements.txt", "requests==2.28.0\n")
        self.write_file("app.py", "from requests import get\n")
        
        graph = build_dependency_graph(self.repo_path, self.req_path)
        self.assertTrue(graph["dependencies"][0]["used"])
        self.assertEqual(graph["files"][0]["imports"][0]["module"], "requests")
        self.assertEqual(graph["files"][0]["imports"][0]["dependency"], "requests")

    def test_standard_library_ignored(self):
        self.write_file("requirements.txt", "numpy==1.23.5\n")
        self.write_file("app.py", "import os\nimport sys\nimport math\n")
        
        graph = build_dependency_graph(self.repo_path, self.req_path)
        self.assertEqual(graph["summary"]["third_party_imports"], 0)
        self.assertEqual(len(graph["files"]), 0)

    def test_local_project_imports_ignored(self):
        self.write_file("requirements.txt", "numpy==1.23.5\n")
        self.write_file("utils.py", "def foo(): pass\n")
        self.write_file("app.py", "import utils\n")
        
        graph = build_dependency_graph(self.repo_path, self.req_path)
        self.assertEqual(graph["summary"]["third_party_imports"], 0)

    def test_yaml_mapping(self):
        self.write_file("requirements.txt", "PyYAML==6.0\n")
        self.write_file("app.py", "import yaml\n")
        
        graph = build_dependency_graph(self.repo_path, self.req_path)
        self.assertTrue(graph["dependencies"][0]["used"])
        self.assertEqual(graph["files"][0]["imports"][0]["module"], "yaml")
        self.assertEqual(graph["files"][0]["imports"][0]["dependency"], "PyYAML")

    def test_unknown_third_party_unresolved(self):
        self.write_file("requirements.txt", "numpy==1.23.5\n")
        self.write_file("app.py", "import some_unknown_lib\n")
        
        graph = build_dependency_graph(self.repo_path, self.req_path)
        self.assertEqual(graph["summary"]["unresolved_imports"], 1)
        self.assertIsNone(graph["files"][0]["imports"][0]["dependency"])

    def test_declared_but_unused(self):
        self.write_file("requirements.txt", "pytest==7.4.0\n")
        self.write_file("app.py", "import os\n")
        
        graph = build_dependency_graph(self.repo_path, self.req_path)
        self.assertFalse(graph["dependencies"][0]["used"])
        self.assertEqual(graph["summary"]["unused_dependencies"], 1)

    def test_multiple_python_source_files(self):
        self.write_file("requirements.txt", "numpy==1.23.5\nrequests==2.34.2\n")
        self.write_file("app1.py", "import numpy\n")
        self.write_file("app2.py", "import requests\n")
        
        graph = build_dependency_graph(self.repo_path, self.req_path)
        self.assertEqual(graph["summary"]["files_analyzed"], 2)
        self.assertEqual(graph["summary"]["used_dependencies"], 2)

    def test_syntax_error_handled(self):
        self.write_file("requirements.txt", "numpy==1.23.5\n")
        self.write_file("app.py", "import numpy\ndef foo(::::\n")
        
        graph = build_dependency_graph(self.repo_path, self.req_path)
        self.assertEqual(graph["summary"]["files_analyzed"], 1)
        self.assertEqual(graph["summary"]["third_party_imports"], 0)

    def test_deterministic_output(self):
        self.write_file("requirements.txt", "numpy==1.23.5\nrequests==2.34.2\n")
        self.write_file("app.py", "import numpy\nimport requests\n")
        
        graph1 = build_dependency_graph(self.repo_path, self.req_path)
        graph2 = build_dependency_graph(self.repo_path, self.req_path)
        self.assertEqual(json.dumps(graph1), json.dumps(graph2))

    def test_json_serialization(self):
        self.write_file("requirements.txt", "numpy==1.23.5\n")
        self.write_file("app.py", "import numpy\n")
        
        graph = build_dependency_graph(self.repo_path, self.req_path)
        try:
            json_str = json.dumps(graph)
            self.assertIn("numpy", json_str)
        except TypeError:
            self.fail("Graph is not JSON serializable")

    def test_utf8_bom_file_imports_detected(self):
        """A source file with a UTF-8 BOM must be parsed successfully
        and its imports must be returned by extract_imports_from_file."""
        self.write_file("requirements.txt", "numpy==1.23.5\n")
        path = os.path.join(self.repo_path, "app.py")
        # Write file with BOM prefix, exactly as Windows editors produce
        with open(path, 'wb') as f:
            f.write(b'\xef\xbb\xbf')  # UTF-8 BOM
            f.write(b'import numpy as np\n')

        graph = build_dependency_graph(self.repo_path, self.req_path)
        self.assertEqual(graph["summary"]["third_party_imports"], 1)
        self.assertTrue(graph["dependencies"][0]["used"])
        self.assertEqual(graph["files"][0]["imports"][0]["module"], "numpy")

    def test_utf8_bom_dependency_mapping(self):
        """A BOM-prefixed file with a third-party import must produce the
        correct dependency mapping in the graph output."""
        self.write_file("requirements.txt", "numpy==1.23.5\nrequests==2.28.0\n")
        path = os.path.join(self.repo_path, "app.py")
        with open(path, 'wb') as f:
            f.write(b'\xef\xbb\xbf')
            f.write(b'import numpy as np\nimport requests\n')

        graph = build_dependency_graph(self.repo_path, self.req_path)
        self.assertEqual(graph["summary"]["used_dependencies"], 2)
        self.assertEqual(graph["summary"]["third_party_imports"], 2)
        modules = [imp["module"] for imp in graph["files"][0]["imports"]]
        self.assertIn("numpy", modules)
        self.assertIn("requests", modules)

    def test_parse_failure_emits_stderr_warning(self):
        """An unparseable file must emit a warning to stderr that
        names the file; it must NOT silently discard the error."""
        import io, contextlib
        self.write_file("requirements.txt", "numpy==1.23.5\n")
        self.write_file("app.py", "def foo(::::\n")  # deliberately broken

        stderr_capture = io.StringIO()
        with contextlib.redirect_stderr(stderr_capture):
            graph = build_dependency_graph(self.repo_path, self.req_path)

        warning_text = stderr_capture.getvalue()
        self.assertIn("[graph] WARNING", warning_text)
        self.assertIn("app.py", warning_text)
        # File is still counted toward files_analyzed
        self.assertEqual(graph["summary"]["files_analyzed"], 1)
        self.assertEqual(graph["summary"]["third_party_imports"], 0)

    def test_files_analyzed_equals_files_length_for_bom_files(self):
        """files_analyzed must equal len(files) when BOM-prefixed source
        files contain third-party imports that can be resolved."""
        self.write_file("requirements.txt", "numpy==1.23.5\nrequests==2.28.0\n")
        # Both files have BOM and each has one resolvable import
        path1 = os.path.join(self.repo_path, "app.py")
        path2 = os.path.join(self.repo_path, "util.py")
        with open(path1, 'wb') as f:
            f.write(b'\xef\xbb\xbf')
            f.write(b'import numpy as np\n')
        with open(path2, 'wb') as f:
            f.write(b'\xef\xbb\xbf')
            f.write(b'import requests\n')

        graph = build_dependency_graph(self.repo_path, self.req_path)
        self.assertEqual(graph["summary"]["files_analyzed"], 2)
        self.assertEqual(len(graph["files"]), 2)
        self.assertEqual(graph["summary"]["used_dependencies"], 2)


if __name__ == '__main__':
    unittest.main()
