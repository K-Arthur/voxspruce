import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import org.kde.plasma.plasmoid

PlasmoidItem {
    id: root
    Plasmoid.icon: "audio-input-microphone"
    toolTipMainText: qsTr("Voice controls")
    toolTipSubText: controlBridge.microphone === "recording"
        ? qsTr("Recording. Open voice controls to finish and review.")
        : controlBridge.state === "recording" ? qsTr("Starting recording. Open voice controls to finish and review.") : qsTr("Open voice controls")
    ControlBridge { id: controlBridge }
    compactRepresentation: CompactControl {
        bridge: controlBridge
        onClicked: root.expanded = !root.expanded
    }
    fullRepresentation: Controls {
        bridge: controlBridge
        Layout.minimumWidth: 240
        Layout.preferredWidth: 360
        Layout.minimumHeight: 240
        Layout.preferredHeight: 500
    }
}
