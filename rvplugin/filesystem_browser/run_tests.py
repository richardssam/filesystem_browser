#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sam Richards
"""
Test runner for the filesystem browser plugin.

Installs lightweight mocks for xstudio's C++ modules before pytest
collects tests, so that the plugin code can be imported without the
full xstudio runtime.

Usage:
    python run_tests.py           # run all tests
    python run_tests.py -v        # verbose
    python run_tests.py -k time   # run only tests matching 'time'
"""

import sys
import types

# ---------------------------------------------------------------------------
# 1.  Mock xstudio C++ modules BEFORE anything else is imported.
# ---------------------------------------------------------------------------

_xstudio_pkg = types.ModuleType("xstudio")
_xstudio_pkg.__path__ = []
sys.modules["xstudio"] = _xstudio_pkg

_xstudio_plugin = types.ModuleType("xstudio.plugin")

class _PluginBase:
    """No-op stand-in for the real C++ PluginBase."""
    def __init__(self, *args, **kwargs):
        pass

_xstudio_plugin.PluginBase = _PluginBase
sys.modules["xstudio.plugin"] = _xstudio_plugin

_xstudio_core = types.ModuleType("xstudio.core")
_xstudio_core.JsonStore = object
_xstudio_core.FrameList = object
_xstudio_core.add_media_atom = None
_xstudio_core.Uuid = object
_xstudio_core.URI = object
sys.modules["xstudio.core"] = _xstudio_core


# ---------------------------------------------------------------------------
# 2.  Run pytest on the tests/ directory, forwarding any CLI args.
# ---------------------------------------------------------------------------

import pytest  # noqa: E402
import os      # noqa: E402

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.exit(pytest.main(["tests/"] + sys.argv[1:]))
