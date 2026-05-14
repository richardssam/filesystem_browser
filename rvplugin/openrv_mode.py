# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sam Richards
"""
OpenRV minor-mode entry point for the Filesystem Browser plugin.

How the abstraction works
-------------------------
filesystem_browser.py is written against xstudio's Python API.  Before it
is imported we install lightweight shims at the xstudio module paths so the
plugin sees a compatible surface without any changes:

    sys.modules["xstudio.plugin"].PluginBase  →  OpenRVPluginBase
    sys.modules["xstudio.core"].AttributeRole →  MockAttributeRole
    (other xstudio.core symbols are no-op stubs)

The host-application interface (media loading) is replaced by swapping
plugin.host after construction:

    plugin.host = OpenRVHostInterface(mode, plugin)

Python → QML channel
--------------------
Every attribute.set_value() call sends a "filesystem-browser-attr-changed"
internal event with JSON payload {"name": attr_name, "value": new_value}.
QML listens via rv.connect(rv, "filesystem-browser-attr-changed", handler).

QML → Python channel
--------------------
QML sends commands by emitting the "filesystem-browser-command" internal
event with a JSON payload matching the plugin's command_channel format:
{"action": "load_file", "path": "/some/file.mov"}.
The mode's _on_browser_command handler routes this to command_attr.set_value(),
which triggers attribute_changed() → the plugin's command dispatch table.

Crash note
----------
sendInternalEvent (→ IPCore::Session::userGenericEvent) must NOT be called
from within activate(), because activate() is itself invoked from within
OpenRV's postInitialize() event dispatch chain.  Re-entering the event
system at that point corrupts Mu's internal state and causes a SIGSEGV in
py2mu (NULL _object*).  OpenRVAttribute._suppress_rv_notify suppresses all
sendInternalEvent calls during plugin construction.
"""

import sys
import os
import types as _types

# Ensure the rvplugin/ directory is on sys.path so both openrv_compat and
# filesystem_browser are importable as packages regardless of how rvpkg sets
# up PYTHONPATH.
_here = os.path.dirname(os.path.abspath(__file__))
if _here not in sys.path:
    sys.path.insert(0, _here)

# ---------------------------------------------------------------------------
# Install xstudio compatibility shims BEFORE importing filesystem_browser
# ---------------------------------------------------------------------------
from openrv_compat.attribute import OpenRVAttribute, MockAttributeRole
from openrv_compat.plugin_base import OpenRVPluginBase
from openrv_compat.host_interface import OpenRVHostInterface

_xs = _types.ModuleType("xstudio")
_xs_plugin = _types.ModuleType("xstudio.plugin")
_xs_core = _types.ModuleType("xstudio.core")

_xs_plugin.PluginBase = OpenRVPluginBase

# Stub out xstudio.core symbols referenced at import time or inside methods.
_xs_core.JsonStore = object
_xs_core.FrameList = object
_xs_core.add_media_atom = None
_xs_core.Uuid = str
_xs_core.URI = str
_xs_core.AttributeRole = MockAttributeRole  # used in attribute_changed()

sys.modules.setdefault("xstudio", _xs)
sys.modules.setdefault("xstudio.plugin", _xs_plugin)
sys.modules.setdefault("xstudio.core", _xs_core)

# ---------------------------------------------------------------------------
# Import the plugin — it now sees our shims in place of xstudio
# ---------------------------------------------------------------------------
from filesystem_browser.filesystem_browser import FilesystemBrowserPlugin


# ---------------------------------------------------------------------------
# OpenRV mode
# ---------------------------------------------------------------------------
try:
    from rv import rvtypes

    class FilesystemBrowserMode(rvtypes.MinorMode):
        """
        OpenRV minor mode that hosts FilesystemBrowserPlugin.
        This class acts as the `connection` argument to the plugin.
        """

        def __init__(self):
            rvtypes.MinorMode.__init__(self)
            self._plugin = None

            # Store bindings/menus as instance variables so the Python objects
            # stay alive for the lifetime of the mode (Mu may store raw
            # PyObject* pointers without Py_INCREF).
            #
            # Menu tuple format confirmed from working OpenRV plugins:
            #   (label, callback, shortcut_or_None, predicate_or_None)
            # The 4th element must be None or a callable — a docstring string
            # in that slot causes Mu to call str() as a function at menu-build
            # time, which raises TypeError, returns NULL from PyObject_Call,
            # and then py2mu(NULL) segfaults at address 0x8 (ob_type).
            # Binding tuple format (from rv/rvtypes.py line 144):
            #   (event_name, callback, docstring)  — exactly 3 elements
            self._global_bindings = [
                ("key-down--b", self._on_toggle_browser,
                 "Toggle Filesystem Browser"),
                ("filesystem-browser-command", self._on_browser_command,
                 "Filesystem Browser Command"),
                ("before-session-deletion", self._on_rv_quit,
                 "Filesystem Browser cleanup on quit"),
            ]
            self._menus = [
                ("View", [
                    ("Filesystem Browser", self._on_toggle_browser,
                     None, None),
                ]),
                ("File", [
                    ("Filesystem Browser", self._on_open_floating,
                     None, None),
                ]),
            ]

            self.init("FilesystemBrowserMode", self._global_bindings, None,
                      self._menus)

        def activate(self):
            rvtypes.MinorMode.activate(self)
            if self._plugin is not None:
                return
            OpenRVAttribute._suppress_rv_notify = True
            try:
                self._plugin = FilesystemBrowserPlugin(self)
                self._plugin.host = OpenRVHostInterface(self, self._plugin)
            except Exception:
                import traceback
                print("FilesystemBrowser: activate() failed:")
                traceback.print_exc()
                self._plugin = None
            finally:
                OpenRVAttribute._suppress_rv_notify = False

        def deactivate(self):
            rvtypes.MinorMode.deactivate(self)
            self._close_browser_window()

        # ------------------------------------------------------------------
        # Event handlers
        # ------------------------------------------------------------------

        def _on_rv_quit(self, event):
            """Called by RV's before-session-deletion event on quit."""
            self._close_browser_window()
            try:
                event.reject()
            except Exception:
                pass

        def _close_browser_window(self):
            """Hide and close any floating QML browser panel."""
            if self._plugin is None:
                return
            try:
                self._plugin._close_qml_windows()
            except Exception as e:
                print(f"FilesystemBrowser: close window error: {e}")

        def _on_toggle_browser(self, event):
            try:
                if self._plugin:
                    self._plugin.toggle_browser(None, "OpenRV")
            except Exception as e:
                print(f"FilesystemBrowser: toggle error: {e}")
            try:
                event.reject()
            except Exception:
                pass

        def _on_open_floating(self, event):
            try:
                if self._plugin:
                    self._plugin.open_floating_browser()
            except Exception as e:
                print(f"FilesystemBrowser: open_floating error: {e}")
            try:
                event.reject()
            except Exception:
                pass

        def _on_browser_command(self, event):
            """
            Route a QML command into the plugin's command_channel attribute,
            which triggers attribute_changed() → the command dispatch table.

            QML example:
                rv.sendInternalEvent(
                    "filesystem-browser-command",
                    JSON.stringify({action: "load_file", path: "/foo/bar.mov"})
                )
            """
            try:
                if self._plugin:
                    self._plugin.command_attr.set_value(event.contents())
            except Exception as e:
                print(f"FilesystemBrowser: command routing error: {e}")
            try:
                event.reject()
            except Exception:
                pass

    # Keep a module-level reference so Python's cyclic GC cannot collect the
    # mode object if OpenRV's C++ layer doesn't Py_INCREF the return value.
    _mode_instance = None

    def createMode():
        global _mode_instance
        _mode_instance = FilesystemBrowserMode()
        return _mode_instance

except ImportError:
    # Not running inside OpenRV (e.g. unit tests or CI).
    def createMode():
        return None
