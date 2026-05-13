// OpenRV shim for xstudio.qml.models.XsAttributeValue
//
// Python → QML: bridge emits attributeChanged(name, jsonStr); we filter by
//   attributeTitle, JSON.parse the string, and update `value`.
//   _fromPython flag prevents the onValueChanged handler echoing it back.
//
// QML → Python: when QML code sets `someAttr.value = x`, onValueChanged
//   calls bridge.setValue() with a JSON.stringify'd string.
//
// All bridge traffic uses str↔str (Signal(str,str) / @Slot(str,str)) so
// PySide6 emits/receives Qt QString and QML never sees PyObjectWrapper.
//
// NOTE: No Component.onCompleted pull — calling Python slots during QML init
// crashes OpenRV (SIGSEGV in PyMethod_New / _PyObject_GC_TRACK via
// PySide6 SignalManager).  Initial values arrive via attributeChanged signals
// emitted by AttributeBridge.emit_all() after engine.load() returns.
import QtQuick 2.15

Item {
    id: root

    property string attributeTitle: ""
    property var    model:          null
    property string role:           "value"
    property var    value:          null

    // Internal: suppresses the Python-echo when we update from a bridge signal.
    property bool _fromPython: false

    // Subscribe to Python-side attribute changes.
    Connections {
        target: root.model ? root.model.bridge : null
        function onAttributeChanged(name, jsonVal) {
            if (name === root.attributeTitle) {
                root._fromPython = true
                try {
                    root.value = JSON.parse(jsonVal)
                } catch (e) {
                    root.value = jsonVal
                }
                root._fromPython = false
            }
        }
    }

    // Forward QML-initiated writes back to Python (e.g. command_channel,
    // current_path).  Skipped when the update came from Python to avoid loops.
    onValueChanged: {
        if (!_fromPython && model && model.bridge && attributeTitle !== "") {
            model.bridge.setValue(attributeTitle, JSON.stringify(value))
        }
    }
}
