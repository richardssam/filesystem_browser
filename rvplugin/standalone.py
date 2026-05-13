#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sam Richards
"""
Standalone Filesystem Browser — no OpenRV required.

Usage:
    python standalone.py [initial_directory]

Opens a floating browser window backed by the real FilesystemBrowserPlugin.
Media operations (load, preview, etc.) are logged to stdout instead of
being sent to a host application.  Everything else — scanning, thumbnails,
directory tree, filtering — runs exactly as it does inside OpenRV.

Useful for:
  • UI / UX iteration without reinstalling the rvpkg on every change
  • Diagnosing thumbnail / scan performance independently of OpenRV overhead
  • Debugging the Python ↔ QML bridge in isolation
"""

import os
import sys
import types as _types

# ---------------------------------------------------------------------------
# Ensure rvplugin/ is on sys.path so openrv_compat and filesystem_browser
# are importable as packages, regardless of where Python was launched from.
# ---------------------------------------------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

# ---------------------------------------------------------------------------
# Qt style: force Fusion (non-native) so that the browser's custom
# backgrounds and content items on controls work without warnings.
# Must be set before QApplication is created.
# ---------------------------------------------------------------------------
os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Fusion")

# ---------------------------------------------------------------------------
# Install xstudio shims BEFORE importing filesystem_browser.
# Mirrors the shim block in openrv_mode.py exactly.
# ---------------------------------------------------------------------------
from openrv_compat.attribute import OpenRVAttribute, MockAttributeRole
from openrv_compat.plugin_base import OpenRVPluginBase

_xs         = _types.ModuleType("xstudio")
_xs_plugin  = _types.ModuleType("xstudio.plugin")
_xs_core    = _types.ModuleType("xstudio.core")

_xs_plugin.PluginBase       = OpenRVPluginBase
_xs_core.JsonStore          = object
_xs_core.FrameList          = object
_xs_core.add_media_atom     = None
_xs_core.Uuid               = str
_xs_core.URI                = str
_xs_core.AttributeRole      = MockAttributeRole

sys.modules.setdefault("xstudio",        _xs)
sys.modules.setdefault("xstudio.plugin", _xs_plugin)
sys.modules.setdefault("xstudio.core",   _xs_core)

# Now safe to import the plugin — it sees our shims instead of xstudio.
from filesystem_browser.filesystem_browser import FilesystemBrowserPlugin


# ---------------------------------------------------------------------------
# Minimal stand-ins for the OpenRV host application objects
# ---------------------------------------------------------------------------

class StandaloneConnection:
    """
    Placeholder for FilesystemBrowserMode (the 'connection' passed to the
    plugin constructor).  The plugin stores it as self.connection but rarely
    calls methods on it — those go through plugin.host instead.
    """
    pass


class StandaloneHostInterface:
    """
    No-op replacement for OpenRVHostInterface.
    Logs media operations to stdout; swap in real logic here if you ever
    want the standalone app to open files in an external player.
    """

    def load_media(self, path):
        print(f"[browser] load: {path}")

    def replace_current_media(self, path):
        print(f"[browser] replace: {path}")

    def compare_with_current_media(self, path):
        print(f"[browser] compare: {path}")

    def append_media(self, path):
        print(f"[browser] append: {path}")

    def preview_media(self, path):
        print(f"[browser] preview: {path}")

    def _clear_preview(self, switch_view=True):
        pass


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    try:
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import Qt
    except ImportError:
        from PySide2.QtWidgets import QApplication
        from PySide2.QtCore import Qt

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Filesystem Browser")

    # Build the plugin — suppress rv event calls during construction
    # (rv isn't available here, but be explicit to match openrv_mode.py).
    OpenRVAttribute._suppress_rv_notify = True
    try:
        plugin = FilesystemBrowserPlugin(StandaloneConnection())
        plugin.host = StandaloneHostInterface()
    except Exception:
        import traceback
        print("standalone: plugin construction failed:")
        traceback.print_exc()
        return 1
    finally:
        OpenRVAttribute._suppress_rv_notify = False

    # If an initial directory was given on the command line, set the
    # current_path attribute before the window opens.
    if len(sys.argv) > 1:
        initial_dir = os.path.abspath(sys.argv[1])
        if os.path.isdir(initial_dir):
            attr = plugin._attributes.get("current_path")
            if attr is not None:
                attr._value = initial_dir   # set without triggering callbacks yet
        else:
            print(f"standalone: not a directory: {initial_dir!r}", file=sys.stderr)

    # Open the floating browser window (creates the QQmlApplicationEngine).
    try:
        plugin.open_floating_browser()
    except Exception:
        import traceback
        print("standalone: open_floating_browser() failed:")
        traceback.print_exc()
        return 1

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
