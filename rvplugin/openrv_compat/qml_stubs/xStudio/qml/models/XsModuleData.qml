// OpenRV shim for xstudio.qml.models.XsModuleData
// Wraps the Python AttributeBridge context property ("xsBridge").
import QtQuick 2.15

QtObject {
    property string modelDataName: ""
    // xsBridge is set as a QML context property by plugin_base.create_qml_item()
    readonly property var bridge: (typeof xsBridge !== "undefined") ? xsBridge : null
}
