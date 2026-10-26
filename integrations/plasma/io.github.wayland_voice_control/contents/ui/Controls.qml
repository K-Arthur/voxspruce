import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ScrollView {
    id: root
    objectName: "voiceControls"
    required property var bridge
    clip: true
    leftPadding: 12
    rightPadding: 12
    topPadding: 12
    bottomPadding: 12
    contentWidth: availableWidth
    implicitWidth: 360
    implicitHeight: 500
    ColumnLayout {
        width: root.availableWidth
        spacing: 12
        Label {
            text: qsTr("Voice controls")
            font.bold: true
            font.pointSize: Qt.application.font.pointSize * 1.25
            Layout.fillWidth: true
            wrapMode: Text.Wrap
        }
        Label {
            objectName: "statusLabel"
            Layout.fillWidth: true
            wrapMode: Text.Wrap
            text: {
                if (!root.bridge.available) return qsTr("Voice controls are closed.")
                if (!root.bridge.compatible) return qsTr("Voice controls need an update.")
                if (root.bridge.practice) return qsTr("Practice · microphone off")
                if (root.bridge.state === "idle" && root.bridge.canStart) return qsTr("Live · ready to record")
                if (root.bridge.state === "recording" && root.bridge.microphone !== "recording") return qsTr("Starting recording…")
                var labels = {idle: qsTr("Idle"), recording: qsTr("Recording"), processing: qsTr("Processing"),
                    reviewing: qsTr("Review in voice controls"), editing: qsTr("Editing in voice controls"),
                    awaiting_second_confirmation: qsTr("Confirmation needed in voice controls"),
                    armed: qsTr("Sending soon. Cancel to stop."), executing: qsTr("Executing confirmed action"), error: qsTr("Attention needed in voice controls")}
                return labels[root.bridge.state] || qsTr("Attention needed in voice controls")
            }
        }
        Label {
            objectName: "setupLabel"
            Layout.fillWidth: true
            wrapMode: Text.Wrap
            text: {
                if (!root.bridge.available) return qsTr("Open controls to start in Practice mode and check setup.")
                if (root.bridge.practice) return qsTr("Practice mode. Open controls to set up live recording.")
                if (!root.bridge.canStart && root.bridge.state !== "recording") return qsTr("Open controls to check the model, microphone, and live setup or review pending work.")
                return qsTr("Record, then finish and review in voice controls before confirming any action.")
            }
        }
        Label {
            objectName: "errorLabel"
            Layout.fillWidth: true
            wrapMode: Text.Wrap
            text: root.bridge.errorText
            visible: text.length > 0
            Accessible.role: Accessible.AlertMessage
        }
        ActionButton {
            objectName: "openControls"
            text: qsTr("Open controls")
            Accessible.name: text
            Layout.fillWidth: true; Layout.minimumHeight: 44
            enabled: !root.bridge.busy
            onClicked: root.bridge.invoke("Show")
        }
        ActionButton {
            objectName: "recordButton"
            text: root.bridge.state === "recording" ? qsTr("Finish and review") : qsTr("Start recording")
            Accessible.name: text
            Layout.fillWidth: true; Layout.minimumHeight: 44
            enabled: root.bridge.available && root.bridge.compatible && !root.bridge.practice && !root.bridge.busy
                     && (root.bridge.state === "recording" || root.bridge.canStart)
            onClicked: root.bridge.invoke(root.bridge.state === "recording" ? "FinishRecording" : "StartRecording")
        }
        Label {
            Layout.fillWidth: true
            wrapMode: Text.Wrap
            text: qsTr("Cancel discards recording or review. Stop closes live access. Quit exits voice controls.")
        }
        ActionButton {
            objectName: "cancelButton"
            text: qsTr("Cancel")
            Accessible.name: text
            Layout.fillWidth: true; Layout.minimumHeight: 44
            enabled: root.bridge.available && root.bridge.compatible && !root.bridge.actionPending("Cancel")
            onClicked: root.bridge.invoke("Cancel")
        }
        ActionButton {
            objectName: "stopButton"
            text: qsTr("Stop")
            Accessible.name: text
            Layout.fillWidth: true; Layout.minimumHeight: 44
            enabled: root.bridge.available && root.bridge.compatible && !root.bridge.actionPending("Stop")
            onClicked: root.bridge.invoke("Stop")
        }
        ActionButton {
            objectName: "quitButton"
            text: qsTr("Quit")
            Accessible.name: text
            Layout.fillWidth: true; Layout.minimumHeight: 44
            enabled: root.bridge.available && root.bridge.compatible && !root.bridge.busy
            onClicked: root.bridge.invoke("Quit")
        }
    }
}
