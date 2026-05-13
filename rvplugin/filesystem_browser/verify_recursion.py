
import unittest
import tempfile
import shutil
import os
import sys

# Add src to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from scanner import FileScanner

class TestRecursionLimit(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.scanner = FileScanner({"max_depth": 2}) # Depth 0, 1, 2
        
    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def create_nested_structure(self):
        # /root
        #   file0.mov
        #   /depth1
        #     file1.mov
        #     /depth2
        #       file2.mov
        #       /depth3
        #         file3.mov
        
        os.makedirs(os.path.join(self.test_dir, "depth1/depth2/depth3"))
        
        with open(os.path.join(self.test_dir, "file0.mov"), "w") as f: f.write("0")
        with open(os.path.join(self.test_dir, "depth1", "file1.mov"), "w") as f: f.write("1")
        with open(os.path.join(self.test_dir, "depth1/depth2", "file2.mov"), "w") as f: f.write("2")
        with open(os.path.join(self.test_dir, "depth1/depth2/depth3", "file3.mov"), "w") as f: f.write("3")

    def test_recursion_limit(self):
        self.create_nested_structure()
        
        # Max Depth 2 means:
        # Depth 0: /root (finds file0.mov)
        # Depth 1: /root/depth1 (finds file1.mov)
        # Depth 2: /root/depth1/depth2 (finds file2.mov)
        # Depth 3: /root/depth1/depth2/depth3 (SKIPPED)
        
        # So we should find file0, file1, file2. NOT file3.
        
        results = self.scanner.scan(self.test_dir)
        names = sorted([r["name"] for r in results])
        
        print(f"Found files: {names}")
        
        self.assertIn("file0.mov", names)
        self.assertIn("file1.mov", names)
        self.assertIn("file2.mov", names)
        self.assertNotIn("file3.mov", names)

    def test_relative_scan(self):
        self.create_nested_structure()
        
        # Scan from depth1
        # Root is depth1.
        # Depth 0: depth1 (finds file1.mov)
        # Depth 1: depth1/depth2 (finds file2.mov)
        # Depth 2: depth1/depth2/depth3 (finds file3.mov)
        
        # So we should find file1, file2, file3.
        
        start_path = os.path.join(self.test_dir, "depth1")
        results = self.scanner.scan(start_path)
        names = sorted([r["name"] for r in results])
        
        print(f"Relative Scan Found files: {names}")
        
        self.assertIn("file1.mov", names)
        self.assertIn("file2.mov", names)
        self.assertIn("file3.mov", names)

if __name__ == "__main__":
    unittest.main()
