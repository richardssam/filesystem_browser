# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sam Richards
"""
Qt QObject bridge that exposes OpenRVAttribute values to QML.

Set as the "xsBridge" context property on the QML engine.
QML stub types XsModuleData / XsAttributeValue bind to it.

All values are JSON-encoded in transit so that PySide6 only ever emits/receives
Python str ↔ Qt QString.  Using Signal(str, object) or @Slot(str, object) causes
PySide6 to pass PyObjectWrapper to QML which QML cannot auto-convert to QString
or double; str/JSON round-trips the values through a type QML knows.

Buffered flush design
---------------------
Plugin worker threads (thumbnail workers, scanner) call set_value() from
background threads.  A naive approach emits attributeChanged immediately,
which causes:
  - Multiple QML model rebuilds per tick when several thumbnails complete
    simultaneously (4 workers × full JSON serialisation of all results).
  - Cross-thread signal delivery latency: Qt queues each emit separately.

Instead, each background set_value() call stores the latest value in a
thread-safe dict (_pending).  A QTimer on the main thread flushes _pending
every FLUSH_INTERVAL_MS, emitting at most one attributeChanged per attribute
per flush.  Thumbnails completing in a 50 ms window → one QML rebuild.

emit_all() bypasses the buffer (called once, from the main thread, after
engine.load() so QML has its initial state immediately).
"""

import json
import threading

try:
    from PySide2.QtCore import QObject, QTimer, Signal, Slot
except ImportError:
    from PySide6.QtCore import QObject, QTimer, Signal, Slot

FLUSH_INTERVAL_MS = 50  # max UI latency for thumbnail / scan updates


def _to_json(val):
    try:
        return json.dumps(val)
    except (TypeError, ValueError):
        return json.dumps(str(val))


class AttributeBridge(QObject):
    """QObject bridge: plugin attributes ↔ QML XsAttributeValue bindings."""

    # (name, json-encoded-value) — both are Qt QString so QML receives them
    # as plain JS strings rather than PySide::PyObjectWrapper.
    attributeChanged = Signal(str, str)

    def __init__(self, plugin, parent=None):
        super().__init__(parent)
        self._plugin = plugin

        # Thread-safe buffer: background threads write here; the main-thread
        # timer reads and emits.  Dict semantics give us free coalescing —
        # rapid updates to the same attribute (e.g. files_attr during thumbnail
        # bursts) are collapsed to a single emit per flush window.
        self._pending = {}
        self._lock = threading.Lock()

        # Subscribe to every attribute before starting the timer so no
        # early callbacks can race with a not-yet-started timer.
        for name in list(plugin._attributes):
            plugin._attributes[name].on_change(self._make_cb(name))

        # Flush timer — lives on the main thread; safe to start here because
        # AttributeBridge is always constructed on the main thread.
        self._flush_timer = QTimer(self)
        self._flush_timer.setInterval(FLUSH_INTERVAL_MS)
        self._flush_timer.timeout.connect(self._flush_pending)
        self._flush_timer.start()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _make_cb(self, name):
        """Return a change callback that buffers the new value thread-safely."""
        def cb(attr, role):
            with self._lock:
                self._pending[name] = _to_json(attr.value())
        return cb

    def _flush_pending(self):
        """Drain the pending buffer and emit one signal per changed attribute."""
        with self._lock:
            if not self._pending:
                return
            snapshot = self._pending
            self._pending = {}
        for name, json_val in snapshot.items():
            self.attributeChanged.emit(name, json_val)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def emit_all(self):
        """Push the current value of every attribute to QML immediately.

        Called once from the main thread after engine.load() returns so QML
        receives its initial state without waiting for the next timer tick.
        Bypasses the buffer intentionally.
        """
        for name, attr in self._plugin._attributes.items():
            try:
                self.attributeChanged.emit(name, _to_json(attr.value()))
            except Exception as e:
                print(f"FilesystemBrowser: emit_all error ({name}): {e}")

    @Slot(str, str)
    def setValue(self, name, json_value):
        """Called from QML to write an attribute (e.g. command_channel).

        json_value is a JSON-encoded string produced by JSON.stringify() in QML.
        Runs on the main thread (QML → Python call), so no lock needed here.
        """
        attr = self._plugin._attributes.get(name)
        if attr:
            try:
                attr.set_value(json.loads(json_value))
            except (json.JSONDecodeError, ValueError):
                attr.set_value(json_value)
