# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sam Richards
"""
OpenRV PluginBase shim: replaces xstudio.plugin.PluginBase.

Implements the attribute, hotkey, menu, and panel APIs that
FilesystemBrowserPlugin calls, so the plugin source is unchanged.

Key design decisions:
  - add_attribute() returns an OpenRVAttribute and wires it to
    attribute_changed() via an on_change callback.
  - register_hotkey() and insert_menu_item() are no-ops here; the
    mode class (FilesystemBrowserMode) pre-registers fixed bindings
    and menus with OpenRV at init time.
  - register_ui_panel_qml() is a no-op; QML panels are declared in
    the PACKAGE file and loaded by rvpkg.
  - create_qml_item() is a stub; floating windows need a
    platform-specific implementation if required.
"""

from openrv_compat.attribute import OpenRVAttribute, MockAttributeRole


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
        self._attributes = {}          # name → OpenRVAttribute

    # ------------------------------------------------------------------
    # Attribute management
    # ------------------------------------------------------------------

    def add_attribute(self, name, value, metadata, register_as_preference=False):
        attr = OpenRVAttribute(name, value)
        # Key by the metadata title when present — QML's XsAttributeValue uses
        # attributeTitle which matches the title, not the internal name.
        # (e.g. name="completions_attribute", title="completions_attr")
        key = name
        if isinstance(metadata, dict):
            key = metadata.get("title", name)
        self._attributes[key] = attr
        # Wire every attribute change back through attribute_changed() so the
        # plugin's command-channel / filter-change logic keeps working.
        attr.on_change(self._dispatch_attribute_changed)
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

            from openrv_compat.attribute_bridge import AttributeBridge
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
