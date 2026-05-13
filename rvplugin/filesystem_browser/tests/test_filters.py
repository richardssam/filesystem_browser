# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sam Richards
"""
Tests for the filtering logic in filesystem_browser.py.

These tests exercise `_apply_filters_logic` which handles:
  - Time filtering (Last 1 day, Last 2 days, Last 1 week, Last 1 month)
  - Version filtering (Latest Version, Latest 2 Versions, All Versions)
  - Empty folder pruning (folders with no surviving files are removed)
"""

import time
import pytest


# -------------------------------------------------------------------------
# Version Filtering
# -------------------------------------------------------------------------

class TestVersionFiltering:

    def test_all_versions_passes_everything(self, mock_plugin, make_file):
        """With 'All Versions', all files should pass through unfiltered."""
        plugin = mock_plugin(filter_version="All Versions")
        results = [
            make_file("shot_v01.exr", "/show/shot/shot_v01.exr", "shot/shot_v01.exr",
                       version=1, version_group="shot", version_rank=1),
            make_file("shot_v02.exr", "/show/shot/shot_v02.exr", "shot/shot_v02.exr",
                       version=2, version_group="shot", is_latest=True, version_rank=0),
            make_file("shot_v03.exr", "/show/shot/shot_v03.exr", "shot/shot_v03.exr",
                       version=3, version_group="shot", is_latest=True, version_rank=0),
        ]
        output = plugin.apply_filters_logic(results)
        names = [r["name"] for r in output]
        assert "shot_v01.exr" in names
        assert "shot_v02.exr" in names
        assert "shot_v03.exr" in names

    def test_latest_version_keeps_only_highest(self, mock_plugin, make_file):
        """With 'Latest Version', only the highest version per group should survive."""
        plugin = mock_plugin(filter_version="Latest Version")
        results = [
            make_file("shot_v01.exr", "/show/shot/shot_v01.exr", "shot/shot_v01.exr",
                       version=1, version_group="shot"),
            make_file("shot_v02.exr", "/show/shot/shot_v02.exr", "shot/shot_v02.exr",
                       version=2, version_group="shot"),
            make_file("shot_v03.exr", "/show/shot/shot_v03.exr", "shot/shot_v03.exr",
                       version=3, version_group="shot", is_latest=True),
        ]
        output = plugin.apply_filters_logic(results)
        names = [r["name"] for r in output]
        assert "shot_v03.exr" in names
        assert "shot_v01.exr" not in names
        assert "shot_v02.exr" not in names

    def test_latest_2_versions(self, mock_plugin, make_file):
        """With 'Latest 2 Versions', only the top 2 per group should survive."""
        plugin = mock_plugin(filter_version="Latest 2 Versions")
        results = [
            make_file("shot_v01.exr", "/show/shot/shot_v01.exr", "shot/shot_v01.exr",
                       version=1, version_group="shot"),
            make_file("shot_v02.exr", "/show/shot/shot_v02.exr", "shot/shot_v02.exr",
                       version=2, version_group="shot"),
            make_file("shot_v03.exr", "/show/shot/shot_v03.exr", "shot/shot_v03.exr",
                       version=3, version_group="shot", is_latest=True),
        ]
        output = plugin.apply_filters_logic(results)
        names = [r["name"] for r in output]
        assert "shot_v03.exr" in names
        assert "shot_v02.exr" in names
        assert "shot_v01.exr" not in names

    def test_ungrouped_files_always_kept(self, mock_plugin, make_file):
        """Files without a version_group should always pass through."""
        plugin = mock_plugin(filter_version="Latest Version")
        results = [
            make_file("random.mov", "/show/random.mov", "random.mov"),
        ]
        output = plugin.apply_filters_logic(results)
        names = [r["name"] for r in output]
        assert "random.mov" in names

    def test_multiple_groups_filtered_independently(self, mock_plugin, make_file):
        """Each version group should be filtered independently."""
        plugin = mock_plugin(filter_version="Latest Version")
        results = [
            make_file("shotA_v01.exr", "/show/shotA_v01.exr", "shotA_v01.exr",
                       version=1, version_group="shotA"),
            make_file("shotA_v02.exr", "/show/shotA_v02.exr", "shotA_v02.exr",
                       version=2, version_group="shotA", is_latest=True),
            make_file("shotB_v01.exr", "/show/shotB_v01.exr", "shotB_v01.exr",
                       version=1, version_group="shotB"),
            make_file("shotB_v03.exr", "/show/shotB_v03.exr", "shotB_v03.exr",
                       version=3, version_group="shotB", is_latest=True),
        ]
        output = plugin.apply_filters_logic(results)
        names = [r["name"] for r in output]
        assert "shotA_v02.exr" in names
        assert "shotB_v03.exr" in names
        assert "shotA_v01.exr" not in names
        assert "shotB_v01.exr" not in names


# -------------------------------------------------------------------------
# Time Filtering
# -------------------------------------------------------------------------

class TestTimeFiltering:

    def test_any_passes_all(self, mock_plugin, make_file):
        """With 'Any', files of any age should pass."""
        plugin = mock_plugin(filter_time="Any")
        old_ts = time.time() - 365 * 86400  # 1 year ago
        results = [
            make_file("old.mov", "/show/old.mov", "old.mov", date=old_ts),
            make_file("new.mov", "/show/new.mov", "new.mov", date=time.time()),
        ]
        output = plugin.apply_filters_logic(results)
        names = [r["name"] for r in output]
        assert "old.mov" in names
        assert "new.mov" in names

    def test_last_1_day(self, mock_plugin, make_file):
        """Only files from the last 24 hours should pass."""
        plugin = mock_plugin(filter_time="Last 1 day")
        now = time.time()
        results = [
            make_file("recent.mov", "/show/recent.mov", "recent.mov", date=now - 3600),
            make_file("old.mov", "/show/old.mov", "old.mov", date=now - 2 * 86400),
        ]
        output = plugin.apply_filters_logic(results)
        names = [r["name"] for r in output]
        assert "recent.mov" in names
        assert "old.mov" not in names

    def test_last_1_week(self, mock_plugin, make_file):
        """Files within 7 days should pass."""
        plugin = mock_plugin(filter_time="Last 1 week")
        now = time.time()
        results = [
            make_file("3days.mov", "/show/3days.mov", "3days.mov", date=now - 3 * 86400),
            make_file("10days.mov", "/show/10days.mov", "10days.mov", date=now - 10 * 86400),
        ]
        output = plugin.apply_filters_logic(results)
        names = [r["name"] for r in output]
        assert "3days.mov" in names
        assert "10days.mov" not in names

    def test_last_1_month(self, mock_plugin, make_file):
        """Files within 30 days should pass."""
        plugin = mock_plugin(filter_time="Last 1 month")
        now = time.time()
        results = [
            make_file("2weeks.mov", "/show/2w.mov", "2w.mov", date=now - 14 * 86400),
            make_file("2months.mov", "/show/2m.mov", "2m.mov", date=now - 60 * 86400),
        ]
        output = plugin.apply_filters_logic(results)
        names = [r["name"] for r in output]
        assert "2weeks.mov" in names
        assert "2months.mov" not in names

    def test_time_filter_does_not_affect_folders(self, mock_plugin, make_file, make_folder):
        """Directories should not be removed by the time filter alone."""
        plugin = mock_plugin(filter_time="Last 1 day")
        now = time.time()
        results = [
            make_folder("mydir", "/show/mydir", "mydir"),
            make_file("recent.mov", "/show/mydir/recent.mov", "mydir/recent.mov",
                       date=now - 3600),
        ]
        output = plugin.apply_filters_logic(results)
        names = [r["name"] for r in output]
        assert "mydir" in names
        assert "recent.mov" in names


# -------------------------------------------------------------------------
# Empty Folder Pruning
# -------------------------------------------------------------------------

class TestEmptyFolderPruning:

    def test_folder_with_files_is_kept(self, mock_plugin, make_file, make_folder):
        """A folder that is an ancestor of a surviving file should be kept."""
        plugin = mock_plugin()
        results = [
            make_folder("shots", "/show/shots", "shots"),
            make_file("comp.exr", "/show/shots/comp.exr", "shots/comp.exr"),
        ]
        output = plugin.apply_filters_logic(results)
        names = [r["name"] for r in output]
        assert "shots" in names
        assert "comp.exr" in names

    def test_empty_folder_is_pruned(self, mock_plugin, make_folder):
        """A folder with no files at all should be removed."""
        plugin = mock_plugin()
        results = [
            make_folder("empty", "/show/empty", "empty"),
        ]
        output = plugin.apply_filters_logic(results)
        names = [r["name"] for r in output]
        assert "empty" not in names

    def test_folder_pruned_when_files_filtered_out(self, mock_plugin, make_file, make_folder):
        """If all files in a folder are filtered out by time, the folder should be pruned."""
        plugin = mock_plugin(filter_time="Last 1 day")
        now = time.time()
        results = [
            make_folder("oldstuff", "/show/oldstuff", "oldstuff"),
            make_file("ancient.mov", "/show/oldstuff/ancient.mov", "oldstuff/ancient.mov",
                       date=now - 30 * 86400),
        ]
        output = plugin.apply_filters_logic(results)
        names = [r["name"] for r in output]
        assert "oldstuff" not in names
        assert "ancient.mov" not in names

    def test_nested_empty_folders_pruned(self, mock_plugin, make_folder):
        """Multiple levels of empty nested folders should all be pruned."""
        plugin = mock_plugin()
        results = [
            make_folder("A", "/show/A", "A"),
            make_folder("B", "/show/A/B", "A/B"),
            make_folder("C", "/show/A/B/C", "A/B/C"),
        ]
        output = plugin.apply_filters_logic(results)
        assert len(output) == 0

    def test_nested_folder_kept_when_deep_file_exists(self, mock_plugin, make_file, make_folder):
        """All ancestor folders should be kept if a deep file survives."""
        plugin = mock_plugin()
        results = [
            make_folder("A", "/show/A", "A"),
            make_folder("B", "/show/A/B", "A/B"),
            make_file("deep.exr", "/show/A/B/deep.exr", "A/B/deep.exr"),
        ]
        output = plugin.apply_filters_logic(results)
        names = [r["name"] for r in output]
        assert "A" in names
        assert "B" in names
        assert "deep.exr" in names


# -------------------------------------------------------------------------
# Combined Filters
# -------------------------------------------------------------------------

class TestCombinedFilters:

    def test_time_and_version_combined(self, mock_plugin, make_file):
        """Time and version filters should both apply."""
        plugin = mock_plugin(filter_time="Last 1 day", filter_version="Latest Version")
        now = time.time()
        results = [
            # Recent v1 — should be filtered by version
            make_file("shot_v01.exr", "/show/shot_v01.exr", "shot_v01.exr",
                       version=1, version_group="shot", date=now - 3600),
            # Recent v2 — should survive (latest + recent)
            make_file("shot_v02.exr", "/show/shot_v02.exr", "shot_v02.exr",
                       version=2, version_group="shot", is_latest=True, date=now - 3600),
            # Old v3 — should be filtered by time
            make_file("shot_v03.exr", "/show/shot_v03.exr", "shot_v03.exr",
                       version=3, version_group="shot", is_latest=True, date=now - 5 * 86400),
        ]
        output = plugin.apply_filters_logic(results)
        names = [r["name"] for r in output]
        # Time filter runs first, removing shot_v03. Then version filter on remaining.
        # After time filter: shot_v01 and shot_v02 remain (both recent).
        # After version filter on group "shot": only shot_v02 (highest version among remaining).
        assert "shot_v02.exr" in names
        assert "shot_v01.exr" not in names
        assert "shot_v03.exr" not in names

    def test_version_filter_prunes_folders(self, mock_plugin, make_file, make_folder):
        """When version filtering removes all files in a folder, the folder is pruned."""
        plugin = mock_plugin(filter_version="Latest Version")
        results = [
            make_folder("old_renders", "/show/old_renders", "old_renders"),
            make_file("shot_v01.exr", "/show/old_renders/shot_v01.exr",
                       "old_renders/shot_v01.exr",
                       version=1, version_group="shot"),
            make_file("shot_v02.exr", "/show/latest/shot_v02.exr",
                       "latest/shot_v02.exr",
                       version=2, version_group="shot", is_latest=True),
            make_folder("latest", "/show/latest", "latest"),
        ]
        output = plugin.apply_filters_logic(results)
        names = [r["name"] for r in output]
        assert "latest" in names
        assert "shot_v02.exr" in names
        assert "old_renders" not in names
        assert "shot_v01.exr" not in names
