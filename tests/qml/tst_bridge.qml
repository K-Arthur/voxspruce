import QtQuick
import QtTest
import "../../integrations/plasma/io.github.wayland_voice_control/contents/ui" as Widget

TestCase {
    name: "ControlBridge"
    QtObject {
        id: fakeBus
        property var calls: []
        function asyncCall(message, resolve, reject) { calls = calls.concat([{message: message, resolve: resolve, reject: reject}]) }
    }
    Component { id: component; Widget.ControlBridge { bus: fakeBus } }
    property var bridge
    function status(changes) {
        var value = {version: 1, practice: false, state: "idle", microphone: "idle", model: "ready", can_start: true, pending_review: false, window_visible: false, background: true}
        for (var key in changes) value[key] = changes[key]
        return value
    }
    function init() { fakeBus.calls = []; bridge = createTemporaryObject(component, this); verify(bridge !== null) }
    function connectService() {
        var count = fakeBus.calls.length
        bridge.updateOwner(":1.100")
        compare(fakeBus.calls.length, count + 1)
        fakeBus.calls[count].resolve({value: status({})})
        verify(bridge.canStart)
    }
    function test_kdeTypedStatusValues() {
        bridge.updateOwner(":1.100")
        var raw = status({version: {value: 1}, state: {value: "recording"}, model: {value: "ready"}, microphone: {value: "recording"}})
        fakeBus.calls[0].resolve({value: raw})
        verify(bridge.compatible)
        compare(bridge.state, "recording")
    }
    function test_absentDoesNotActivate() { compare(fakeBus.calls.length, 0); verify(!bridge.canStart) }
    function test_successfulQuitDoesNotReadDisappearingService() {
        connectService()
        bridge.invoke("Quit")
        compare(fakeBus.calls.length, 2)
        fakeBus.calls[1].resolve({value: true})
        compare(fakeBus.calls.length, 2)
        compare(bridge.errorText, "")
    }
    function test_methodsAndDuplicates() {
        connectService(); bridge.invoke("StartRecording"); bridge.invoke("StartRecording")
        compare(fakeBus.calls.length, 2)
        bridge.invoke("Cancel"); bridge.invoke("Stop")
        compare(fakeBus.calls.length, 4)
        fakeBus.calls[1].resolve({value: true}); verify(!bridge.actionPending("StartRecording"))
    }
    function test_staleReplyAfterOwnerLoss() {
        bridge.updateOwner(":1.100"); var old = fakeBus.calls[0]
        bridge.updateOwner(""); old.resolve({value: status({})})
        verify(!bridge.available); verify(!bridge.canStart); compare(bridge.model, "idle")
        bridge.updateOwner(":1.101"); old.resolve({value: status({})})
        verify(!bridge.canStart)
    }
    function test_signalWinsOverEarlierGetStatus() {
        bridge.updateOwner(":1.100"); var old = fakeBus.calls[0]
        bridge.receiveStatus(status({state: "recording", microphone: "recording", can_start: false}))
        old.resolve({value: status({})}); compare(bridge.state, "recording"); verify(!bridge.canStart)
    }
    function test_sanitizeAndVersion() {
        connectService()
        bridge.receiveStatus(status({state: "secret transcript", model: "/private/model", microphone: "raw error"}))
        compare(bridge.state, "error"); compare(bridge.model, "error"); compare(bridge.microphone, "idle")
        verify(!bridge.canStart)
        bridge.receiveStatus(status({version: 2})); verify(!bridge.compatible); verify(!bridge.canStart)
        bridge.invoke("StartRecording"); compare(fakeBus.calls.length, 1)
    }
    function test_failuresAreFixedAndNeverRetried() {
        bridge.invoke("Show"); compare(fakeBus.calls.length, 1)
        fakeBus.calls[0].reject({message: "PRIVATE TEXT"})
        verify(bridge.errorText.indexOf("Open controls") >= 0)
        verify(bridge.errorText.indexOf("PRIVATE") < 0); compare(fakeBus.calls.length, 1)
        connectService(); bridge.invoke("StartRecording")
        fakeBus.calls[fakeBus.calls.length - 1].resolve({value: false})
        verify(bridge.errorText.length > 0)
    }
}
