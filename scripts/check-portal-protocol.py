"""Exercise real Gio signatures on a private D-Bus; never uses the host portal.

Run with PYTHONPATH=src .venv/bin/python scripts/check-portal-protocol.py.
The subprocess owns its fake portal, emits early responses, and records keys in
memory. No compositor input, permission UI, microphone, or network is involved.
"""

import subprocess
import sys

if __name__ == "__main__" and "--isolated-child" not in sys.argv:
    raise SystemExit(
        subprocess.call(
            ["dbus-run-session", "--", sys.executable, __file__, "--isolated-child"]
        )
    )

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib

from wayland_voice_control.domain import Mode, Workflow
from wayland_voice_control.gio_transport import GioWire, dispatch
from wayland_voice_control.portal import GlobalShortcuts, RemoteDesktop
from wayland_voice_control.transport import (
    DESKTOP,
    DESTINATION,
    REQUEST,
    SESSION,
    RequestTransport,
)

bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
name_result = bus.call_sync(
    "org.freedesktop.DBus",
    "/org/freedesktop/DBus",
    "org.freedesktop.DBus",
    "RequestName",
    GLib.Variant("(su)", (DESTINATION, 0)),
    None,
    Gio.DBusCallFlags.NONE,
    1000,
    None,
).unpack()[0]
assert name_result == 1, (
    "Refusing to run unless this process owns the fake portal name."
)
xml = """<node>
<interface name="org.freedesktop.portal.RemoteDesktop">
<method name="CreateSession"><arg type="a{sv}" direction="in"/><arg type="o" direction="out"/></method>
<method name="SelectDevices"><arg type="o" direction="in"/><arg type="a{sv}" direction="in"/><arg type="o" direction="out"/></method>
<method name="Start"><arg type="o" direction="in"/><arg type="s" direction="in"/><arg type="a{sv}" direction="in"/><arg type="o" direction="out"/></method>
<method name="NotifyKeyboardKeysym"><arg type="o" direction="in"/><arg type="a{sv}" direction="in"/><arg type="i" direction="in"/><arg type="u" direction="in"/></method>
</interface>
<interface name="org.freedesktop.portal.GlobalShortcuts">
<method name="CreateSession"><arg type="a{sv}" direction="in"/><arg type="o" direction="out"/></method>
<method name="BindShortcuts"><arg type="o" direction="in"/><arg type="a(sa{sv})" direction="in"/><arg type="s" direction="in"/><arg type="a{sv}" direction="in"/><arg type="o" direction="out"/></method>
</interface></node>"""
session_xml = """<node><interface name="org.freedesktop.portal.Session"><method name="Close"/><signal name="Closed"><arg type="a{sv}"/></signal></interface></node>"""
remote_session = DESKTOP + "/session/fake/remote"
shortcut_session = DESKTOP + "/session/fake/shortcuts"
events = []
options_seen = []
errors = []
shortcut_events = []
registrations = []
loop = GLib.MainLoop()


def fail(message):
    errors.append(str(message))
    loop.quit()


def method(connection, sender, path, interface, method, parameters, invocation):
    try:
        args = parameters.unpack()
        if method == "NotifyKeyboardKeysym":
            events.append(args)
            invocation.return_value(GLib.Variant("()", ()))
            return
        if method == "Close":
            invocation.return_value(GLib.Variant("()", ()))
            return
        options = args[-1]
        options_seen.append((method, options))
        handle = (
            DESKTOP
            + "/request/"
            + sender[1:].replace(".", "_")
            + "/"
            + options["handle_token"]
        )
        result = {}
        if method == "CreateSession":
            session = (
                remote_session
                if interface.endswith("RemoteDesktop")
                else shortcut_session
            )
            result = {"session_handle": GLib.Variant("s", session)}
        elif method == "SelectDevices":
            assert options["types"] == 1 and options["persist_mode"] == 0
        elif method == "Start":
            result = {"devices": GLib.Variant("u", 1)}
        elif method == "BindShortcuts":
            assert len(args[1]) == 3
            result = {
                "shortcuts": GLib.Variant(
                    "a(sa{sv})",
                    [
                        (
                            key,
                            {
                                "trigger_description": GLib.Variant(
                                    "s", "Assigned " + key
                                )
                            },
                        )
                        for key, _ in args[1]
                    ],
                )
            }
        connection.emit_signal(
            None, handle, REQUEST, "Response", GLib.Variant("(ua{sv})", (0, result))
        )
        invocation.return_value(GLib.Variant("(o)", (handle,)))
    except (AssertionError, ValueError, TypeError, GLib.Error) as exc:
        invocation.return_dbus_error("org.freedesktop.DBus.Error.Failed", str(exc))
        fail(exc)


for interface in Gio.DBusNodeInfo.new_for_xml(xml).interfaces:
    registrations.append(bus.register_object(DESKTOP, interface, method, None, None))
for path in [remote_session, shortcut_session]:
    registrations.append(
        bus.register_object(
            path,
            Gio.DBusNodeInfo.new_for_xml(session_xml).interfaces[0],
            method,
            None,
            None,
        )
    )
transport = RequestTransport(GioWire(bus), timeout=2)
remote = RemoteDesktop(transport, dispatch=dispatch, on_closed=lambda: finish())
shortcuts = GlobalShortcuts(
    transport, lambda key, active: shortcut_events.append((key, active))
)


def finish():
    try:
        assert not remote.granted
        assert len(events) == 6, events
        assert [e[2:] for e in events] == [
            (ord("H"), 1),
            (ord("H"), 0),
            (0x010003BB, 1),
            (0x010003BB, 0),
            (ord("."), 1),
            (ord("."), 0),
        ]
        assert shortcut_events == [
            ("hold_to_talk", True),
            ("hold_to_talk", False),
            ("confirm", False),
        ], shortcut_events
        assert shortcuts.bindings["confirm"] == "Assigned confirm"
        print(
            "PASS: real Gio async requests, early Response signals, keyboard-only options, Unicode key events, shortcut events and revocation on isolated D-Bus"
        )
    except (AssertionError, ValueError, TypeError, GLib.Error) as exc:
        errors.append(str(exc))
    shortcuts.close()
    loop.quit()


def shortcuts_bound(ok, error):
    if error or not ok:
        fail(error)
        return
    for signal, key in [
        ("Activated", "hold_to_talk"),
        ("Activated", "hold_to_talk"),
        ("Deactivated", "hold_to_talk"),
        ("Deactivated", "confirm"),
        ("Activated", "confirm"),
        ("Deactivated", "confirm"),
    ]:
        bus.emit_signal(
            None,
            DESKTOP,
            "org.freedesktop.portal.GlobalShortcuts",
            signal,
            GLib.Variant("(osta{sv})", (shortcut_session, key, 0, {})),
        )
    GLib.timeout_add(
        30,
        lambda: (
            bus.emit_signal(
                None, remote_session, SESSION, "Closed", GLib.Variant("(a{sv})", ({},))
            ),
            False,
        )[1],
    )


def sent(error):
    if error:
        fail(error)
    else:
        shortcuts.connect(shortcuts_bound)


def connected(ok, error):
    if error or not ok:
        fail(error)
        return
    w = Workflow()
    w.set_permission(True)
    w.set_microphone_consent(True)
    rid = w.begin_recording(Mode.DICTATION)
    w.finish_recording(rid)
    action = w.receive_transcript(rid, "Hλ.")
    w.confirm(action.id)
    remote.execute(w.take_action(action.id), sent)


remote.connect(connected)
GLib.timeout_add_seconds(5, lambda: (fail("timeout"), False)[1])
loop.run()
if errors:
    print("FAIL:", errors)
    sys.exit(1)
