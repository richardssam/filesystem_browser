# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sam Richards
"""
OpenRV PluginBase shim: replaces xstudio.plugin.PluginBase.

Implements the attribute, hotkey, menu, and panel APIs that
FilesystemBrowserPlugin calls, so the plugin source is unchanged.

Key design decisions:
  - add_attribute() returns an OpenRVAttribute and wires it to
    attribute_changed() via an on_change callback.
  - Attributes created with register_as_preference=True are persisted to
    a JSON file (~/.config/filesystem_browser/prefs.json on Unix/macOS,
    %APPDATA%/filesystem_browser/prefs.json on Windows).  The saved value
    is restored on the next launch before the plugin reads the attribute.
    Saves are debounced to 1 s so rapid changes (navigation, filter edits)
    don't hammer the disk.
  - register_hotkey() and insert_menu_item() are no-ops here; the
    mode class (FilesystemBrowserMode) pre-registers fixed bindings
    and menus with OpenRV at init time.
  - register_ui_panel_qml() is a no-op; QML panels are declared in
    the PACKAGE file and loaded by rvpkg.
  - create_qml_item() is a stub; floating windows need a
    platform-specific implementation if required.
"""

import os
import json
import threading

from openrv_compat.attribute import OpenRVAttribute, MockAttributeRole


def _default_prefs_path():
    if os.name == "nt":
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
    else:
        base = os.path.expanduser("~/.config")
    prefs_dir = os.path.join(base, "filesystem_browser")
    os.makedirs(prefs_dir, exist_ok=True)
    return os.path.join(prefs_dir, "prefs.json")


class OpenRVPluginBase:
    """
    Drop-in replacement for xstudio.plugin.PluginBase.

    The `connection` argument receives the FilesystemBrowserMode instance
    (the OpenRV minor mode), which acts as the host-application handle.
    """

    def __init__(self, connection, name, qml_folder=None):
        self.connection = connection   # FilesystemBrowserMode (or None in tests)
        self._plugin_name = name
        self._qml_folder = qml_folder
        self._attributes = {}          # key → OpenRVAttribute
        self._pref_keys = set()        # keys of preference attributes
        self._prefs_file = _default_prefs_path()
        self._saved_prefs = self._load_prefs()
        self._save_timer = None
        self._save_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Preference persistence
    # ------------------------------------------------------------------

    def _load_prefs(self):
        try:
            with open(self._prefs_file, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {}

    def _schedule_save(self):
        """Debounced save: write to disk 1 s after the last change."""
        with self._save_lock:
            if self._save_timer is not None:
                self._save_timer.cancel()
            t = threading.Timer(1.0, self._flush_prefs)
            t.daemon = True
            t.start()
            self._save_timer = t

    def _flush_prefs(self):
        with self._save_lock:
            self._save_timer = None
        data = {}
        for key in self._pref_keys:
            attr = self._attributes.get(key)
            if attr is not None:
                data[key] = attr.value()
        try:
            with open(self._prefs_file, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2)
        except OSError as e:
            print(f"FilesystemBrowser: could not save prefs to {self._prefs_file}: {e}")

    # ------------------------------------------------------------------
    # Attribute management
    # ------------------------------------------------------------------

    def add_attribute(self, name, value, metadata, register_as_preference=False):
        # Key by the metadata title when present — QML's XsAttributeValue uses
        # attributeTitle which matches the title, not the internal name.
        key = name
        if isinstance(metadata, dict):
            key = metadata.get("title", name)

        # Restore persisted value before the plugin reads it for the first time.
        if register_as_preference and key in self._saved_prefs:
            value = self._saved_prefs[key]

        attr = OpenRVAttribute(name, value)
        self._attributes[key] = attr
        attr.on_change(self._dispatch_attribute_changed)

        if register_as_preference:
            self._pref_keys.add(key)
            attr.on_change(lambda _a, _r: self._schedule_save())

        return attr

    def _dispatch_attribute_changed(self, attribute, role):
        try:
            self.attribute_changed(attribute, role)
        except Exception as e:
            print(f"FilesystemBrowser: attribute_changed error ({attribute.name}): {e}")

    def attribute_changed(self, attribute, role):
        """Override in subclass to react to attribute changes."""
        pass

    # ------------------------------------------------------------------
    # Hotkeys — collected but not acted on here.
    # FilesystemBrowserMode registers a fixed "b" binding with OpenRV.
    # ------------------------------------------------------------------

    def register_hotkey(self, callback, keycode, modifier, name, description,
                        auto_repeat=False, component="", context=""):
        return keycode  # Return keycode as a stable UUID substitute

    # ------------------------------------------------------------------
    # Menus — pre-registered in FilesystemBrowserMode.init()
    # ------------------------------------------------------------------

    def insert_menu_item(self, menu, label, path, position=0.0,
                         hotkey_uuid=None, callback=None):
        pass

    # ------------------------------------------------------------------
    # QML panel — declared in PACKAGE; loaded by rvpkg at startup
    # ------------------------------------------------------------------

    def register_ui_panel_qml(self, name, qml_snippet, position=0.0,
                               icon="", extra=-1.0, action_uuid=None):
        pass

    def _close_qml_windows(self):
        # Hide immediately so the window disappears even if close() is deferred.
        for item in getattr(self, '_qml_items', []):
            try:
                item.hide()
            except Exception:
                pass
            try:
                item.close()
            except Exception:
                pass
        # Restore terminal echo that Qt/Cocoa may have disabled when it took
        # over keyboard input.  This ensures the launching terminal is usable
        # after OpenRV exits.
        try:
            import sys
            if sys.stdin.isatty():
                saved = getattr(self, '_saved_termios', None)
                if saved is not None:
                    import termios
                    termios.tcsetattr(sys.stdin, termios.TCSANOW, saved)
                else:
                    import os
                    os.system('stty echo 2>/dev/null')
        except Exception:
            pass

    def create_qml_item(self, qml_str):
        """Create a floating QML window via PySide2/PySide6 + QQmlApplicationEngine.

        Import paths added to the engine:
          • filesystem_browser/qml/  — provides the FilesystemBrowser 1.0 module
          • openrv_compat/qml_stubs/ — provides xStudio 1.0 and xstudio.qml.models 1.0

        The Python AttributeBridge is set as context property "xsBridge" so that
        XsModuleData / XsAttributeValue stubs can read and write plugin attributes.
        """
        import os, re, tempfile
        _pyside_pkg = None
        try:
            try:
                from PySide2.QtQml import QQmlApplicationEngine
                from PySide2.QtCore import QUrl
            except ImportError:
                from PySide6.QtQml import QQmlApplicationEngine
                from PySide6.QtCore import QUrl
                import PySide6 as _pyside_pkg
        except ImportError:
            print("FilesystemBrowser: PySide2/PySide6 not available — cannot show panel")
            return

        if not hasattr(self, '_qml_engine'):
            this_dir = os.path.dirname(os.path.abspath(__file__))
            python_dir = os.path.dirname(this_dir)
            qml_import_path = os.path.join(python_dir, "filesystem_browser", "qml")
            stubs_dir = os.path.join(this_dir, "qml_stubs")

            # Locate Qt's QML module directory so QtQuick.Window, QtQuick.Controls, etc. resolve.
            # PySide6 (as shipped by OpenRV) keeps its QML plugins at <package>/Qt/qml/.
            qt_qml_path = None
            if _pyside_pkg is not None:
                candidate = os.path.join(os.path.dirname(_pyside_pkg.__file__), "Qt", "qml")
                if os.path.isdir(os.path.join(candidate, "QtQuick")):
                    qt_qml_path = candidate

            # Fallback: QLibraryInfo (works when Qt is not embedded in a Python package).
            if not qt_qml_path:
                try:
                    try:
                        from PySide2.QtCore import QLibraryInfo
                        qt_qml_path = QLibraryInfo.location(QLibraryInfo.Qml2ImportsPath)
                    except ImportError:
                        from PySide6.QtCore import QLibraryInfo
                        qt_qml_path = QLibraryInfo.path(QLibraryInfo.Qml2ImportsPath)
                except Exception:
                    pass

            # Snapshot terminal state before Qt starts handling keyboard input.
            # Restored in _close_qml_windows so the launching terminal is
            # left in a sane state after OpenRV exits.
            try:
                import sys as _sys, termios as _termios
                if _sys.stdin.isatty():
                    self._saved_termios = _termios.tcgetattr(_sys.stdin)
            except Exception:
                pass

            from openrv_compat.attribute_bridge import AttributeBridge
            try:
                try:
                    from PySide2.QtQuickControls2 import QQuickStyle
                except ImportError:
                    from PySide6.QtQuickControls2 import QQuickStyle
                QQuickStyle.setStyle("Material")
            except Exception:
                pass

            engine = QQmlApplicationEngine()
            if qt_qml_path:
                engine.addImportPath(qt_qml_path)
            else:
                print("FilesystemBrowser: WARNING — could not find Qt QML import path")
            engine.addImportPath(qml_import_path)
            engine.addImportPath(stubs_dir)
            self._qml_bridge = AttributeBridge(self)
            engine.rootContext().setContextProperty("xsBridge", self._qml_bridge)
            self._qml_engine = engine
            self._qml_items = []

            # Close all floating windows when the host application quits so
            # the browser panel doesn't outlive OpenRV.
            try:
                try:
                    from PySide2.QtWidgets import QApplication
                except ImportError:
                    from PySide6.QtWidgets import QApplication
                app = QApplication.instance()
                if app is not None:
                    app.aboutToQuit.connect(self._close_qml_windows)
            except Exception:
                pass

        # The QML snippet uses FilesystemBrowser but doesn't import it — inject
        # the import statement after the first existing import line.
        if "FilesystemBrowser" in qml_str and "import FilesystemBrowser" not in qml_str:
            qml_str = re.sub(
                r'(import\s+\S[^\n]*\n)',
                r'\1import FilesystemBrowser 1.0\n',
                qml_str, count=1,
            )

        # Qt5 / PySide2 has no QQmlApplicationEngine.loadData(); write to a
        # temp file and load by URL (the engine has parsed everything by the
        # time load() returns, so the file can be deleted immediately).
        tmp = tempfile.NamedTemporaryFile(
            suffix='.qml', mode='w', delete=False, encoding='utf-8')
        try:
            tmp.write(qml_str)
            tmp.close()
            before = len(self._qml_engine.rootObjects())
            self._qml_engine.load(QUrl.fromLocalFile(tmp.name))
            self._qml_items.extend(self._qml_engine.rootObjects()[before:])
            # Push initial attribute values to QML now that loading is complete.
            # Done here (not during Component.onCompleted) to avoid a SIGSEGV
            # in PySide6's SignalManager when Python slots are called from QML
            # during synchronous QML initialisation.
            self._qml_bridge.emit_all()
        except Exception as e:
            print(f"FilesystemBrowser: QML load error: {e}")
        finally:
            try:
                os.unlink(tmp.name)
            except OSError:
                pass
