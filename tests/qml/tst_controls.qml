import QtQuick
import QtQuick.Controls
import QtTest
import "../../integrations/plasma/io.github.wayland_voice_control/contents/ui" as Widget

TestCase {
    name: "VoiceControls"
    width: 360; height: 640
    when: windowShown
    visible: true
    QtObject {
        id: fake
        property bool available: true
        property bool compatible: true
        property bool practice: false
        property string state: "idle"
        property string microphone: "idle"
        property string model: "ready"
        property bool canStart: true
        property bool pendingReview: false
        property string errorText: ""
        property var pending: ({})
        property var calls: []
        function actionPending(method) { return !!pending[method] }
        property bool busy: false
        function invoke(method) { calls = calls.concat([method]) }
    }
    Component { id: component; Widget.Controls { bridge: fake; width: 320; height: 600 } }
    property var view
    function init() {
        fake.available = true; fake.compatible = true; fake.practice = false
        fake.state = "idle"; fake.microphone = "idle"; fake.canStart = true; fake.errorText = ""; fake.busy = false
        fake.pending = ({}); fake.calls = []
        view = createTemporaryObject(component, this)
        verify(view !== null)
        wait(1)
    }
    function button(name) { return findChild(view, name) }
    function test_startFinish() {
        mouseClick(button("recordButton")); compare(fake.calls[0], "StartRecording")
        fake.state = "recording"; fake.canStart = false
        compare(button("recordButton").text, "Finish and review")
        mouseClick(button("recordButton")); compare(fake.calls[1], "FinishRecording")
    }
    function test_practiceAndUnready() {
        fake.practice = true; verify(!button("recordButton").enabled)
        verify(findChild(view, "setupLabel").text.indexOf("Open controls") >= 0)
        fake.practice = false; fake.canStart = false
        verify(!button("recordButton").enabled)
        mouseClick(button("openControls")); compare(fake.calls[0], "Show")
    }
    function test_emergencyDuringPending() {
        fake.busy = true; verify(!button("recordButton").enabled)
        mouseClick(button("cancelButton")); mouseClick(button("stopButton"))
        compare(fake.calls.join(","), "Cancel,Stop")
        fake.pending = ({Stop: true}); verify(!button("stopButton").enabled)
    }
    function test_serviceLossAndError() {
        fake.available = false; fake.canStart = false
        verify(!button("recordButton").enabled); verify(!button("stopButton").enabled)
        verify(button("openControls").enabled)
        fake.errorText = "Could not contact voice controls. Open controls to try again."
        tryCompare(findChild(view, "errorLabel"), "visible", true)
    }
    function test_actualCompactControlKeyboardAndRecordingName() {
        var component = Qt.createComponent("../../integrations/plasma/io.github.wayland_voice_control/contents/ui/CompactControl.qml")
        compare(component.status, Component.Ready, component.errorString())
        var compact = createTemporaryObject(component, this, {bridge: fake, width: 44, height: 44})
        verify(compact !== null)
        compare(compact.Accessible.name, "Open voice controls")
        compare(compact.icon.name, "audio-input-microphone")
        fake.state = "recording"; fake.microphone = "loading"
        verify(compact.Accessible.name.indexOf("Starting recording") >= 0)
        fake.microphone = "recording"
        verify(compact.Accessible.name.indexOf("Recording") >= 0)
        compare(compact.icon.name, "media-record")
        var clicks = 0
        compact.clicked.connect(function() { clicks++ })
        compact.forceActiveFocus(); verify(compact.activeFocus)
        keyClick(Qt.Key_Space); compare(clicks, 1)
    }
    function test_innerSpacing() { compare(view.leftPadding, 12); compare(view.rightPadding, 12); compare(view.topPadding, 12); compare(view.bottomPadding, 12) }
    function test_keyboardAndAccessibleNames() {
        var open = button("openControls")
        compare(open.Accessible.name, "Open controls")
        open.forceActiveFocus(); verify(open.activeFocus)
        keyClick(Qt.Key_Space); compare(fake.calls[0], "Show")
        keyClick(Qt.Key_Tab); verify(button("recordButton").activeFocus)
        verify(button("recordButton").height >= 44)
    }
    function test_narrowLargeTextWrapsAndScrollsToQuit() {
        view.width = 240; view.height = 320; view.font.pointSize = Qt.application.font.pointSize * 4
        fake.state = "recording"; fake.canStart = false
        wait(20)
        var record = button("recordButton")
        compare(record.contentItem.wrapMode, Text.Wrap)
        verify(!record.contentItem.truncated)
        verify(record.height >= record.contentItem.paintedHeight)
        verify(view.contentHeight > view.availableHeight)
        view.contentItem.contentY = view.contentHeight - view.availableHeight
        wait(20)
        var quit = button("quitButton"), point = quit.mapToItem(view, quit.width / 2, quit.height / 2)
        verify(point.y > 0 && point.y < view.height)
        mouseClick(quit); compare(fake.calls[0], "Quit")
    }
    function test_protocolMismatch() {
        fake.compatible = false
        verify(!button("recordButton").enabled)
        verify(!button("cancelButton").enabled)
        verify(button("openControls").enabled)
    }
}
