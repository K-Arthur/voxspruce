// Run by scripts/check-widget-protocol.py, which supplies a private activation bus.
import QtQuick
import QtTest
import org.kde.plasma.workspace.dbus as DBus
import "@WIDGET_UI@" as Widget

TestCase {
    name: "ActualGtkWidgetProtocol"
    Widget.ControlBridge { id: bridge }
    Component { id: observerFactory; Widget.ControlBridge {} }
    function helper(method) {
        var target = bridge.owner
        verify(target.length > 0, "test helper requires the current unique service owner")
        var done = false, failure = ""
        DBus.SessionBus.asyncCall({service: target, path: "/WidgetTest",
            iface: "io.github.wayland_voice_control.WidgetTest1", member: method, signature: "", arguments: []},
            function() { done = true }, function(reply) {
                failure = reply.error.name + ": " + reply.error.message
                done = true
            })
        tryVerify(function() { return done }, 5000)
        verify(failure.length === 0, "test helper " + method + " for " + target + " (current " + bridge.owner + ") failed: " + failure)
    }
    function invoke(method) {
        bridge.invoke(method)
        tryVerify(function() { return !bridge.busy }, 5000)
    }
    function test_fullLifecycle() {
        verify(!bridge.available)
        wait(100)
        verify(!bridge.available, "status reading activated the application")
        bridge.invoke("Show")
        tryVerify(function() { return bridge.available && bridge.compatible }, 8000)
        verify(bridge.practice); verify(!bridge.canStart)
        helper("Ready")
        tryVerify(function() { return bridge.canStart }, 5000)
        var observer = createTemporaryObject(observerFactory, this)
        tryVerify(function() { return observer.available && observer.compatible }, 5000)
        compare(observer.owner, bridge.owner)
        verify(observer.canStart)
        invoke("StartRecording")
        tryCompare(bridge, "state", "recording", 5000)
        invoke("FinishRecording")
        helper("Complete")
        tryVerify(function() { return bridge.pendingReview }, 5000)
        compare(bridge.state, "reviewing")
        invoke("Cancel")
        tryVerify(function() { return !bridge.pendingReview }, 5000)
        invoke("Stop")
        tryVerify(function() { return !bridge.canStart }, 5000)
        var oldOwner = bridge.owner
        helper("Crash")
        tryVerify(function() { return !bridge.available }, 5000)
        verify(!bridge.canStart); compare(bridge.model, "idle")
        bridge.invoke("Show")
        tryVerify(function() { return bridge.available && bridge.compatible }, 8000)
        verify(bridge.owner !== oldOwner)
        verify(bridge.practice); verify(!bridge.canStart)
        helper("DisableActivation")
        invoke("Quit")
        tryVerify(function() { return !bridge.available }, 5000)
        invoke("Show")
        verify(bridge.errorText.indexOf("Open controls") >= 0)
        verify(!bridge.available)
    }
}
