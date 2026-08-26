import os
import tempfile
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "tools")))
from transaction import Transaction

class TestTransaction(unittest.TestCase):
    def test_snapshot_and_rollback(self):
        with tempfile.TemporaryDirectory() as tmp_path:
            f = os.path.join(tmp_path, "test.txt")
            with open(f, "w", encoding="utf-8") as file:
                file.write("original content")
            
            tx = Transaction()
            tx.snapshot(f)
            
            with open(f, "w", encoding="utf-8") as file:
                file.write("modified content")
            
            tx.rollback()
            with open(f, "r", encoding="utf-8") as file:
                self.assertEqual(file.read(), "original content")

    def test_multiple_files(self):
        with tempfile.TemporaryDirectory() as tmp_path:
            f1 = os.path.join(tmp_path, "req.txt")
            f2 = os.path.join(tmp_path, "app.py")
            with open(f1, "w", encoding="utf-8") as file: file.write("req original")
            with open(f2, "w", encoding="utf-8") as file: file.write("app original")
            
            tx = Transaction()
            tx.snapshot(f1)
            tx.snapshot(f2)
            
            with open(f1, "w", encoding="utf-8") as file: file.write("req mod")
            with open(f2, "w", encoding="utf-8") as file: file.write("app mod")
            
            tx.rollback()
            with open(f1, "r", encoding="utf-8") as file: self.assertEqual(file.read(), "req original")
            with open(f2, "r", encoding="utf-8") as file: self.assertEqual(file.read(), "app original")

    def test_duplicate_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp_path:
            f = os.path.join(tmp_path, "test.txt")
            with open(f, "w", encoding="utf-8") as file: file.write("v1")
            
            tx = Transaction()
            tx.snapshot(f)
            
            with open(f, "w", encoding="utf-8") as file: file.write("v2")
            tx.snapshot(f) # Should do nothing
            
            with open(f, "w", encoding="utf-8") as file: file.write("v3")
            tx.rollback()
            
            with open(f, "r", encoding="utf-8") as file: self.assertEqual(file.read(), "v1")

    def test_commit(self):
        with tempfile.TemporaryDirectory() as tmp_path:
            f = os.path.join(tmp_path, "test.txt")
            with open(f, "w", encoding="utf-8") as file: file.write("original")
            
            tx = Transaction()
            tx.snapshot(f)
            with open(f, "w", encoding="utf-8") as file: file.write("modified")
            
            tx.commit()
            with self.assertRaises(RuntimeError):
                tx.rollback()
                
            with open(f, "r", encoding="utf-8") as file: self.assertEqual(file.read(), "modified")

    def test_pre_existing_user_modification(self):
        with tempfile.TemporaryDirectory() as tmp_path:
            f = os.path.join(tmp_path, "app.py")
            with open(f, "w", encoding="utf-8") as file: file.write("base")
            
            # User edits it
            with open(f, "w", encoding="utf-8") as file: file.write("base + user edit")
            
            tx = Transaction()
            tx.snapshot(f)
            
            # DepGraph edits
            with open(f, "w", encoding="utf-8") as file: file.write("base + user edit + depgraph edit")
            
            tx.rollback()
            with open(f, "r", encoding="utf-8") as file: self.assertEqual(file.read(), "base + user edit")

    def test_multiple_patches_in_one_transaction(self):
        with tempfile.TemporaryDirectory() as tmp_path:
            f = os.path.join(tmp_path, "app.py")
            with open(f, "w", encoding="utf-8") as file: file.write("original")
            
            tx = Transaction()
            tx.snapshot(f)
            
            with open(f, "w", encoding="utf-8") as file: file.write("patch 1")
            with open(f, "w", encoding="utf-8") as file: file.write("patch 2")
            
            tx.rollback()
            with open(f, "r", encoding="utf-8") as file: self.assertEqual(file.read(), "original")

if __name__ == '__main__':
    unittest.main()
