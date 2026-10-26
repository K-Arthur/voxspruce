import QtQuick
import org.kde.plasma.components as PlasmaComponents

PlasmaComponents.ToolButton {
    id: root
    required property var bridge
    readonly property bool recording: bridge.microphone === "recording"
    readonly property bool starting: bridge.state === "recording" && !recording
    readonly property string statusDescription: recording
        ? qsTr("Recording. Open voice controls to finish and review.")
        : starting ? qsTr("Starting recording. Open voice controls to finish and review.") : qsTr("Open voice controls")
    icon.name: recording ? "media-record" : "audio-input-microphone"
    Accessible.name: recording ? qsTr("Recording — open voice controls")
        : starting ? qsTr("Starting recording — open voice controls") : qsTr("Open voice controls")
    Accessible.description: statusDescription
    activeFocusOnTab: true
}
