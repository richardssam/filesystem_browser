# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sam Richards
"""
conftest.py — pytest fixtures for filesystem browser tests.

NOTE: xstudio mocks are installed by run_tests.py (the test runner script)
before pytest runs. This conftest only provides fixtures.
"""

import os
import sys
import json
import time
import importlib.util
import pytest


# ---------------------------------------------------------------------------
# Load the plugin module directly by file path to bypass the package's
# __init__.py (which re-exports create_plugin_instance).
# ---------------------------------------------------------------------------

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_module_path = os.path.join(PLUGIN_DIR, "filesystem_browser.py")

_spec = importlib.util.spec_from_file_location(
    "filesystem_browser_module", _module_path
)
_fb_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_fb_module)

FilesystemBrowserPlugin = _fb_module.FilesystemBrowserPlugin

# Make scanner importable for test_scanner.py
if PLUGIN_DIR not in sys.path:
    sys.path.insert(0, PLUGIN_DIR)


# ---------------------------------------------------------------------------
# Mock attribute helper
# ---------------------------------------------------------------------------

class MockAttribute:
    """Mock for xstudio XsAttributeValue — stores a value and tracks calls."""

    def __init__(self, initial_value=None):
        self._value = initial_value
        self.set_value_calls = []

    def value(self):
        return self._value

    def set_value(self, val):
        self._value = val
        self.set_value_calls.append(val)


class MockPlugin:
    """
    Wraps the real _apply_filters_logic from FilesystemBrowserPlugin
    but replaces all xstudio attribute accesses with simple mocks.
    """

    def __init__(self, filter_time="Any", filter_version="All Versions"):
        self.cached_filter_time = filter_time
        self.cached_filter_version = filter_version
        self.files_attr = MockAttribute()

    def apply_filters_logic(self, results):
        """Invoke the real method with this mock as `self`, return parsed output."""
        FilesystemBrowserPlugin._apply_filters_logic(self, results)
        return json.loads(self.files_attr.set_value_calls[-1])


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_plugin():
    """Factory that creates MockPlugin instances with given filter settings."""
    def _factory(filter_time="Any", filter_version="All Versions"):
        return MockPlugin(filter_time=filter_time, filter_version=filter_version)
    return _factory


def _make_file(name, path, relpath, version=None, version_group=None,
               date=None, is_latest=False, version_rank=0):
    """Build a file entry dict matching the scanner output format."""
    item = {
        "name": name,
        "path": path,
        "relpath": relpath,
        "is_folder": False,
        "type": "File",
    }
    if version is not None:
        item["version"] = version
    if version_group is not None:
        item["version_group"] = version_group
    if date is not None:
        item["date"] = date
    item["is_latest_version"] = is_latest
    item["version_rank"] = version_rank
    return item


def _make_folder(name, path, relpath):
    """Build a folder entry dict matching the scanner output format."""
    return {
        "name": name,
        "path": path,
        "relpath": relpath,
        "is_folder": True,
        "type": "Folder",
    }


@pytest.fixture
def make_file():
    return _make_file


@pytest.fixture
def make_folder():
    return _make_folder
