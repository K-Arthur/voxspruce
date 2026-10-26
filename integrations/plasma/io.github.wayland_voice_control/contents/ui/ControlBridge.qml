import QtQuick
import org.kde.plasma.workspace.dbus as DBus

// Only the fixed Controls1 protocol crosses this boundary. A unique owner is used
// for every call except explicit Show, so status reads cannot activate the app.
Item {
    id: root
    property var bus: DBus.SessionBus
    readonly property string service: "io.github.wayland_voice_control"
    readonly property string path: "/io/github/wayland_voice_control/Controls"
    readonly property string iface: "io.github.wayland_voice_control.Controls1"
    property string owner: ""
    property int epoch: 0
    property int revision: 0
    property int ownerQuery: 0
    readonly property bool available: owner !== ""
    property bool compatible: false
    property bool practice: true
    property string state: "idle"
    property string microphone: "idle"
    property string model: "idle"
    property bool canStart: false
    property bool pendingReview: false
    property string errorText: ""
    property var pending: ({})
    readonly property bool busy: Object.keys(pending).length > 0

    function actionPending(method) { return !!pending[method] }
    function setPending(method, value) {
        var next = Object.assign({}, pending)
        if (value) next[method] = true
        else delete next[method]
        pending = next
    }
    function failure() {
        errorText = qsTr("Could not contact voice controls. Open controls to try again.")
    }
    function updateOwner(newOwner) {
        if (owner === newOwner) return
        epoch++; revision++; ownerQuery++
        owner = newOwner
        compatible = false; practice = true; state = "idle"
        microphone = "idle"; model = "idle"; canStart = false
        pendingReview = false; pending = ({})
        if (owner !== "") refresh()
    }
    function discoverOwner() {
        var query = ++ownerQuery
        bus.asyncCall({service: "org.freedesktop.DBus", path: "/org/freedesktop/DBus",
                       iface: "org.freedesktop.DBus", member: "GetNameOwner", signature: "(s)", arguments: [service]},
                      function(reply) { if (query === ownerQuery) updateOwner(scalar(reply.value)) },
                      function() { if (query === ownerQuery) updateOwner("") })
    }
    function scalar(value) {
        // KDE preserves D-Bus integer/string signatures as typed value objects.
        return value !== null && typeof value === "object" && value.value !== undefined ? value.value : value
    }
    function applyStatus(raw) {
        compatible = raw !== null && raw !== undefined && scalar(raw.version) === 1
        if (!compatible) {
            practice = true; state = "error"; microphone = "idle"; model = "idle"
            canStart = false; pendingReview = false
            errorText = qsTr("Voice controls need a compatible update. Open controls to continue.")
            return
        }
        var states = ["idle", "recording", "processing", "reviewing", "editing", "awaiting_second_confirmation", "armed", "executing", "error"]
        state = states.indexOf(scalar(raw.state)) >= 0 ? scalar(raw.state) : "error"
        microphone = ["idle", "loading", "recording", "processing"].indexOf(scalar(raw.microphone)) >= 0 ? scalar(raw.microphone) : "idle"
        model = ["idle", "loading", "ready", "error"].indexOf(scalar(raw.model)) >= 0 ? scalar(raw.model) : "error"
        practice = raw.practice !== false
        canStart = raw.can_start === true && !practice && state === "idle" && model === "ready" && microphone === "idle"
        pendingReview = raw.pending_review === true
        errorText = ""
    }
    function receiveStatus(raw) {
        if (!available) return
        revision++
        applyStatus(raw)
    }
    function refresh() {
        if (!available) return
        var generation = epoch, serial = revision
        bus.asyncCall({service: owner, path: path, iface: iface, member: "GetStatus", signature: "", arguments: []},
                      function(reply) { if (generation === epoch && serial === revision) applyStatus(reply.value) },
                      function() { if (generation === epoch && serial === revision) { canStart = false; failure() } })
    }
    function invoke(method) {
        if (["Show", "StartRecording", "FinishRecording", "Cancel", "Stop", "Quit"].indexOf(method) < 0) return
        if (actionPending(method)) return
        var emergency = method === "Cancel" || method === "Stop"
        if (!emergency && busy) return
        if (method !== "Show" && (!available || !compatible)) return
        if (method === "StartRecording" && !canStart) return
        if (method === "FinishRecording" && state !== "recording") return
        var generation = epoch
        setPending(method, true); errorText = ""
        bus.asyncCall({service: available ? owner : service, path: path, iface: iface, member: method, signature: "", arguments: []},
                      function(reply) {
                          if (generation !== epoch) return
                          setPending(method, false)
                          if (reply.value !== true) failure()
                          else refresh()
                      }, function() {
                          if (generation !== epoch) return
                          setPending(method, false); failure()
                      })
    }
    DBus.DBusServiceWatcher {
        watchedService: root.service
        busType: DBus.BusType.Session
        onRegisteredChanged: {
            if (registered) root.discoverOwner()
            else root.updateOwner("")
        }
        Component.onCompleted: { if (registered) root.discoverOwner() }
    }
    DBus.SignalWatcher {
        service: "org.freedesktop.DBus"
        path: "/org/freedesktop/DBus"
        iface: "org.freedesktop.DBus"
        function dbusActivatableServicesChanged() {}
        function dbusNameOwnerChanged(name, oldOwner, newOwner) {
            if (root.scalar(name) === root.service) root.updateOwner(root.scalar(newOwner))
        }
    }
    DBus.SignalWatcher {
        enabled: root.available
        service: root.owner
        path: root.path
        iface: root.iface
        function dbusStatusChanged(status) { root.receiveStatus(status) }
    }
}
