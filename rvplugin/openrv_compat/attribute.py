# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sam Richards
"""
Attribute shim: replaces xstudio's XsAttributeValue and AttributeRole for OpenRV.

When running inside OpenRV, every set_value() call sends a
"filesystem-browser-attr-changed" internal event so QML can react.
The event payload is JSON: {"name": attr_name, "value": new_value}.

QML should listen for this event via:
    rv.connect(rv, "filesystem-browser-attr-changed", function(event) { ... })

Thread safety note: sendInternalEvent is called from whatever thread calls
set_value(). The search worker calls set_value() from a background thread.
If OpenRV's event dispatch is not thread-safe this may need to be queued
through a main-thread timer; this is a known limitation of the current port.
"""

import uuid as _uuid
import json

try:
    import rv.extra_commands as _rvExtra
    _RV_AVAILABLE = True
except ImportError:
    _RV_AVAILABLE = False


class MockAttributeRole:
    """Replaces xstudio.core.AttributeRole."""
    Value = "Value"


class OpenRVAttribute:
    """
    Drop-in replacement for xstudio's XsAttributeValue.

    Stores a value, fires Python callbacks on change (used by plugin_base to
    dispatch attribute_changed()), and forwards updates to OpenRV QML via
    the "filesystem-browser-attr-changed" internal event.
    """

    # Set True during plugin construction to suppress sendInternalEvent calls.
    # Calling sendInternalEvent from within activate(), which runs inside
    # OpenRV's postInitialize() event dispatch chain, causes re-entrant event
    # processing that crashes Mu's interpreter (SIGSEGV in py2mu with NULL
    # _object* — visible in crash trace at IPCore::Session::userGenericEvent).
    _suppress_rv_notify = False

    def __init__(self, name, initial_value):
        self.name = name
        self._value = initial_value
        self.uuid = str(_uuid.uuid4())
        self._change_callbacks = []

    def value(self):
        return self._value

    def set_value(self, val):
        self._value = val
        self._notify_rv(val)
        for cb in list(self._change_callbacks):
            try:
                cb(self, MockAttributeRole.Value)
            except Exception as e:
                print(f"OpenRVAttribute '{self.name}' callback error: {e}")

    def expose_in_ui_attrs_group(self, group_name):
        pass  # No-op: OpenRV doesn't use attribute groups

    def on_change(self, callback):
        self._change_callbacks.append(callback)

    def _notify_rv(self, val):
        """Send an internal event so QML can react to the value change."""
        if not _RV_AVAILABLE or OpenRVAttribute._suppress_rv_notify:
            return
        try:
            payload = json.dumps({"name": self.name, "value": val})
            _rvExtra.sendInternalEvent("filesystem-browser-attr-changed", payload)
        except Exception:
            pass  # Best-effort; QML will get the next update
