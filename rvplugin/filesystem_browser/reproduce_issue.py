
import unittest
import tempfile
import shutil
import os
import sys

# Add src to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from scanner import FileScanner

class TestDeepSequence(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.scanner_default = FileScanner() # Should be 6 now? No, FileScanner default is still 3 unless passed. 
        # Wait, FileScanner default in scanner.py line 25: self.config.get("max_depth", 3)
        # I changed the plugin default, but not the scanner default!
        # I should change scanner.py default too.
        self.scanner_old = FileScanner({"max_depth": 3})
        self.scanner_new = FileScanner({"max_depth": 6})
        
    def test_version_grouping(self):
        # Create mock items manually to test _group_versions isolation
        scanner = self.scanner_default
        
        items = [
            {"name": "shot_v01.exr", "path": "/p/shot_v01.exr"},
            {"name": "shot_v02.exr", "path": "/p/shot_v02.exr"},
            {"name": "shot_v10.exr", "path": "/p/shot_v10.exr"},
            {"name": "other_v05.exr", "path": "/p/other_v05.exr"}
        ]
        
        grouped = scanner._group_versions(items)
        
        # Verify only one is latest for 'shot'
        shot_items = [i for i in grouped if "shot_" in i["name"]]
        self.assertEqual(len(shot_items), 3)
        
        latests = [i for i in shot_items if i.get("is_latest_version")]
        self.assertEqual(len(latests), 1, f"Expected 1 latest, found {len(latests)}: {latests}")
        self.assertEqual(latests[0]["version"], 10)
        
        # Verify other group
        other_items = [i for i in grouped if "other_" in i["name"]]
        self.assertEqual(len(other_items), 1)
        self.assertTrue(other_items[0]["is_latest_version"])
        shutil.rmtree(self.test_dir)

    def create_deep_structure(self):
        # /pix
        #   bg
        #     v1
        #       lin
        #         2kfa
        #           file.exr (SEQUENCE)
        
        path = os.path.join(self.test_dir, "bg/v1/lin/2kfa")
        os.makedirs(path)
        # Create sequence
        for i in range(1, 4):
            with open(os.path.join(path, f"file.{i:04d}.exr"), "w") as f: f.write("0")

    def test_limit_impact(self):
        self.create_deep_structure()
        
        # Test old limit (3) - should fail
        results = self.scanner_old.scan(self.test_dir)
        names = [r["name"] for r in results]
        # Should not find sequence at depth 5
        found = any("file" in n for n in names)
        self.assertFalse(found, f"Found file with limit 3: {names}")
        
        # Test new limit (6) - should succeed
        results = self.scanner_new.scan(self.test_dir)
        names = [r["name"] for r in results]
        
        print(f"Depth 6 results: {names}")
        found = any("file" in n for n in names)
        # We expect a sequence now, e.g. file.@@@@.exr
        self.assertTrue(found, f"Did not find file/sequence with limit 6: {names}")

        # Test default limit (should also be 6 now)
        results = self.scanner_default.scan(self.test_dir)
        names = [r["name"] for r in results]
        found = any("file" in n for n in names)
        self.assertTrue(found)

if __name__ == "__main__":
    unittest.main()
