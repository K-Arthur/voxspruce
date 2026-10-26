"""Exercise real Gio signatures on a private D-Bus; never uses the host portal.

Run with PYTHONPATH=src .venv/bin/python scripts/check-portal-protocol.py.
The subprocess owns its fake portal, emits early responses, and records keys in
memory. No compositor input, permission UI, microphone, or network is involved.
"""

import os
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
    GLib.Variant("(su)", (DESTINATION, 1)),
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
shortcut_changes = []
registrations = []
pending_hook = None
loop = GLib.MainLoop()


def fail(message):
    errors.append(str(message))
    loop.quit()


def method(connection, sender, path, interface, method, parameters, invocation):
    global pending_hook
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
            assert options["types"] == 1 and options["persist_mode"] == 0, (
                f"Expected keyboard-only, nonpersistent access options; received {options!r}"
            )
        elif method == "Start":
            result = {"devices": GLib.Variant("u", 1)}
        elif method == "BindShortcuts":
            expected_ids = {"hold_to_talk", "confirm", "cancel", "show_controls"}
            requested_ids = [key for key, _ in args[1]]
            assert set(requested_ids) == expected_ids, (
                f"Expected shortcut IDs {sorted(expected_ids)!r}; received {requested_ids!r}"
            )
            assert len(requested_ids) == len(expected_ids), (
                f"Expected each shortcut ID once; received {requested_ids!r}"
            )
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
        if (
            pending_hook is not None
            and method == "CreateSession"
            and interface.endswith("RemoteDesktop")
        ):
            hook, pending_hook = pending_hook, None
            invocation.return_value(GLib.Variant("(o)", (handle,)))
            GLib.idle_add(lambda: (hook(connection, handle, result), False)[1])
            return
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
    transport,
    lambda key, active: shortcut_events.append((key, active)),
    on_changed=lambda keys: shortcut_changes.append(keys),
)


def finish():
    try:
        assert not remote.granted, (
            "Remote keyboard grant survived portal session closure"
        )
        assert len(events) == 6, f"Expected six Unicode key events; received {events!r}"
        assert [e[2:] for e in events] == [
            (ord("H"), 1),
            (ord("H"), 0),
            (0x010003BB, 1),
            (0x010003BB, 0),
            (ord("."), 1),
            (ord("."), 0),
        ], f"Unexpected Unicode keysym press/release sequence: {events!r}"
        assert shortcut_events == [
            ("hold_to_talk", True),
            ("hold_to_talk", False),
            ("confirm", False),
            ("show_controls", False),
            ("hold_to_talk", True),
            ("confirm", False),
        ], (
            f"Unexpected shortcut events (Show controls must fire once on release): {shortcut_events!r}"
        )
        assert shortcut_changes == [frozenset({"confirm"})], shortcut_changes
        assert shortcuts.bindings["confirm"] == "Updated confirm", (
            f"Unexpected confirm binding description: {shortcuts.bindings!r}"
        )
        assert shortcuts.bindings["show_controls"] == "Assigned show_controls", (
            f"Missing Show controls binding description: {shortcuts.bindings!r}"
        )

    except (AssertionError, ValueError, TypeError, GLib.Error) as exc:
        errors.append(str(exc))
    shortcuts.close()
    if errors:
        loop.quit()
    else:
        owner_loss_checks()


def owner_loss_checks():
    """Use actual bus owner transitions, including direct name replacement."""
    replacement = Gio.DBusConnection.new_for_address_sync(
        os.environ["DBUS_SESSION_BUS_ADDRESS"],
        Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT
        | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION,
        None,
        None,
    )
    for interface in Gio.DBusNodeInfo.new_for_xml(xml).interfaces:
        registrations.append(
            replacement.register_object(DESKTOP, interface, method, None, None)
        )
    for path in (remote_session, shortcut_session):
        registrations.append(
            replacement.register_object(
                path,
                Gio.DBusNodeInfo.new_for_xml(session_xml).interfaces[0],
                method,
                None,
                None,
            )
        )
    lost = []
    remote.on_closed = lambda: lost.append("remote")
    shortcuts.on_closed = lambda: lost.append("shortcuts")

    def name_call(connection, operation, flags=None):
        return connection.call_sync(
            "org.freedesktop.DBus",
            "/org/freedesktop/DBus",
            "org.freedesktop.DBus",
            operation,
            GLib.Variant(
                "(s)" if flags is None else "(su)",
                (DESTINATION,) if flags is None else (DESTINATION, flags),
            ),
            None,
            Gio.DBusCallFlags.NONE,
            1000,
            None,
        ).unpack()[0]

    def check(mode):
        try:
            assert not remote.granted, f"Keyboard grant survived portal owner {mode}"
            assert not shortcuts.bindings, (
                f"Shortcut bindings survived portal owner {mode}"
            )
            assert lost == ["remote", "shortcuts"], (
                f"Unexpected owner loss callbacks: {lost!r}"
            )
            if mode == "disappearance":
                assert name_call(bus, "RequestName", 1) == 1
                lost.clear()
                establish("replacement")
            else:
                replacement.close_sync(None)
                GLib.timeout_add(20, pending_connection_loss)
        except (AssertionError, GLib.Error) as exc:
            fail(exc)
        return False

    def pending_connection_loss():
        global pending_hook
        pending_lost, completions = [], []
        pending_remote = RemoteDesktop(
            transport, dispatch=dispatch, on_closed=lambda: pending_lost.append(True)
        )

        def verify_late():
            try:
                assert not pending_remote.granted, (
                    "Late Response restored a lost pending grant"
                )
                assert pending_lost == [True], pending_lost
                assert not any(ok for ok, _error in completions), completions
                print(
                    "PASS: real Gio requests, early responses, Unicode keys, shortcut changes, session closure, portal disappearance/replacement and pending-connection loss on isolated D-Bus"
                )
                loop.quit()
            except AssertionError as exc:
                fail(exc)
            return False

        def owner_gone(connection, handle, result):
            try:
                assert not pending_remote.granted, (
                    "Pending grant survived portal owner loss"
                )
                assert pending_lost == [True], pending_lost
                connection.emit_signal(
                    None,
                    handle,
                    REQUEST,
                    "Response",
                    GLib.Variant("(ua{sv})", (0, result)),
                )
                GLib.timeout_add(20, verify_late)
            except (AssertionError, GLib.Error) as exc:
                fail(exc)
            return False

        def created(connection, handle, result):
            try:
                assert name_call(bus, "ReleaseName") == 1
                GLib.timeout_add(20, lambda: owner_gone(connection, handle, result))
            except (AssertionError, GLib.Error) as exc:
                fail(exc)

        pending_hook = created
        pending_remote.connect(lambda *args: completions.append(args))
        return False

    def establish(mode):
        def bound(ok, error):
            if not ok or error:
                fail(error)
                return
            if mode == "disappearance":
                assert name_call(bus, "ReleaseName") == 1
            else:
                assert name_call(replacement, "RequestName", 2) == 1
            GLib.timeout_add(50, lambda: check(mode))

        def granted(ok, error):
            if not ok or error:
                fail(error)
                return
            shortcuts.connect(bound)

        remote.connect(granted)

    establish("disappearance")


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
        ("Deactivated", "show_controls"),  # Unpaired release is ignored.
        ("Activated", "show_controls"),
        ("Activated", "show_controls"),  # Repeated press is ignored.
        ("Deactivated", "show_controls"),
        ("Deactivated", "show_controls"),  # Repeated release is ignored.
    ]:
        bus.emit_signal(
            None,
            DESKTOP,
            "org.freedesktop.portal.GlobalShortcuts",
            signal,
            GLib.Variant("(osta{sv})", (shortcut_session, key, 0, {})),
        )
    for key in ("confirm", "hold_to_talk"):
        bus.emit_signal(
            None,
            DESKTOP,
            "org.freedesktop.portal.GlobalShortcuts",
            "Activated",
            GLib.Variant("(osta{sv})", (shortcut_session, key, 0, {})),
        )
    bus.emit_signal(
        None,
        DESKTOP,
        "org.freedesktop.portal.GlobalShortcuts",
        "ShortcutsChanged",
        GLib.Variant(
            "(oa(sa{sv}))",
            (
                shortcut_session,
                [
                    (
                        "confirm",
                        {"trigger_description": GLib.Variant("s", "Updated confirm")},
                    )
                ],
            ),
        ),
    )
    for key in ("confirm", "hold_to_talk"):
        for signal in ("Activated", "Deactivated"):
            bus.emit_signal(
                None,
                DESKTOP,
                "org.freedesktop.portal.GlobalShortcuts",
                signal,
                GLib.Variant("(osta{sv})", (shortcut_session, key, 0, {})),
            )
    for signal in ("Activated", "Deactivated"):
        bus.emit_signal(
            None,
            DESKTOP,
            "org.freedesktop.portal.GlobalShortcuts",
            signal,
            GLib.Variant("(osta{sv})", (shortcut_session, "confirm", 0, {})),
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
