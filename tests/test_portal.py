import unittest

from wayland_voice_control.domain import ActionKind, PendingAction, Risk
from wayland_voice_control.portal import GlobalShortcuts, RemoteDesktop, keysym
from wayland_voice_control.transport import RequestTransport


class FakeTransport:
    def __init__(self):
        self.requests = []
        self.closed = []
        self.signals = {}
        self.keys = []
        self.fail_key = None

    def request(self, interface, method, signature, args, options, callback):
        request = [interface, method, signature, args, options, callback, False]
        self.requests.append(request)
        return lambda: request.__setitem__(6, True)

    def reply(self, results=None, code=0, index=-1):
        self.requests[index][5](code, results or {}, None)

    def close_session(self, path):
        self.closed.append(path)

    def subscribe(self, interface, signal, path, callback):
        token = max(self.signals, default=0) + 1
        self.signals[token] = (interface, signal, path, callback)
        return token

    def unsubscribe(self, token):
        self.signals.pop(token, None)

    def subscribe_owner_lost(self, callback):
        return self.subscribe("dbus", "owner_lost", None, callback)

    def lose_owner(self):
        for token, entry in list(self.signals.items()):
            if token in self.signals and entry[1] == "owner_lost":
                entry[3]()

    def notify_key(self, session, symbol, state):
        self.keys.append((session, symbol, state))
        if self.fail_key == (symbol, state):
            raise RuntimeError("input failed")


class FakeWire:
    unique_name = ":1.25"

    def __init__(self):
        self.events = []
        self.callback = None
        self.expire = None
        self.owner_callbacks = {}

    def subscribe(self, interface, signal, path, callback):
        self.events.append(("subscribe", path))
        self.callback = callback
        return 7

    def subscribe_owner_lost(self, callback):
        self.owner_callbacks[8] = callback
        return 8

    def unsubscribe(self, token):
        self.owner_callbacks.pop(token, None)
        self.events.append(("unsubscribe", token))

    def call(self, interface, method, path, signature, args, callback):
        self.events.append((method, path, args))
        if method != "Close":
            self.method_done = callback

    def schedule(self, seconds, callback):
        self.expire = callback
        return lambda: self.events.append(("unschedule",))


class RequestTests(unittest.TestCase):
    def test_subscribes_before_call_and_checks_handle(self):
        wire = FakeWire()
        responses = []
        transport = RequestTransport(wire, token_factory=lambda: "abc")
        transport.request(
            "remote",
            "Start",
            "(osa{sv})",
            ("/session", ""),
            {},
            lambda *result: responses.append(result),
        )
        path = "/org/freedesktop/portal/desktop/request/1_25/abc"
        self.assertEqual(wire.events[0], ("subscribe", path))
        self.assertEqual(wire.events[1][0], "Start")
        wire.method_done(("/wrong",), None)
        self.assertIsNotNone(responses[0][2])
        self.assertIn(("unsubscribe", 7), wire.events)

    def test_response_before_method_reply_is_delivered_once(self):
        wire = FakeWire()
        results = []
        RequestTransport(wire, token_factory=lambda: "abc").request(
            "remote", "CreateSession", "(a{sv})", (), {}, lambda *x: results.append(x)
        )
        wire.callback((0, {"session_handle": "/session"}))
        wire.method_done(("/org/freedesktop/portal/desktop/request/1_25/abc",), None)
        self.assertEqual(results, [(0, {"session_handle": "/session"}, None)])

    def test_owner_loss_finishes_pending_request_and_ignores_late_success(self):
        wire, results = FakeWire(), []
        RequestTransport(wire, token_factory=lambda: "abc").request(
            "remote", "Start", "(a{sv})", (), {}, lambda *x: results.append(x)
        )
        self.assertEqual(len(wire.owner_callbacks), 1)
        next(iter(wire.owner_callbacks.values()))()
        self.assertEqual(len(results), 1)
        self.assertIsInstance(results[0][2], RuntimeError)
        wire.callback((0, {"devices": 1}))
        wire.method_done(("/org/freedesktop/portal/desktop/request/1_25/abc",), None)
        self.assertEqual(len(results), 1)
        self.assertEqual(wire.owner_callbacks, {})

    def test_timeout_and_cancel_close_request_and_unsubscribe(self):
        for timeout in (True, False):
            wire = FakeWire()
            results = []
            cancel = RequestTransport(wire, token_factory=lambda: "abc").request(
                "remote",
                "Start",
                "(a{sv})",
                (),
                {},
                lambda *x, results=results: results.append(x),
            )
            wire.expire() if timeout else cancel()
            self.assertEqual(len(results), 1)
            self.assertIsNotNone(results[0][2])
            self.assertIn(("unsubscribe", 7), wire.events)
            self.assertTrue(any(e[0] == "Close" for e in wire.events))
            wire.callback((0, {}))
            self.assertEqual(len(results), 1)


class RemoteTests(unittest.TestCase):
    def setUp(self):
        self.transport = FakeTransport()
        self.events = []
        self.remote = RemoteDesktop(
            self.transport, dispatch=lambda f: f(), run_worker=lambda f: f()
        )

    def grant(self):
        self.remote.connect(lambda *x: self.events.append(x))
        self.transport.reply({"session_handle": "/session"})
        self.assertEqual(self.transport.requests[-1][4]["types"], 1)
        self.assertEqual(self.transport.requests[-1][4]["persist_mode"], 0)
        self.transport.reply()
        self.transport.reply({"devices": 1})

    def test_requires_keyboard_grant_and_closes_failed_session(self):
        self.remote.connect(lambda *x: self.events.append(x))
        self.transport.reply({"session_handle": "/session"})
        self.transport.reply()
        self.transport.reply({"devices": 2})
        self.assertFalse(self.remote.granted)
        self.assertIn("/session", self.transport.closed)
        self.assertIsNotNone(self.events[-1][1])

    def test_stop_during_connect_closes_late_grant(self):
        self.remote.connect(lambda *x: self.events.append(x))
        self.remote.close()
        self.transport.reply({"session_handle": "/late"})
        self.assertIn("/late", self.transport.closed)
        self.assertFalse(self.remote.granted)

    def test_input_only_after_grant_and_releases_after_error(self):
        action = PendingAction(
            "a", ActionKind.COMMAND, "previous_field", Risk.NORMAL, 0, 30
        )
        done = []
        self.remote.execute(action, lambda error: done.append(error))
        self.assertIsNotNone(done[-1])
        self.assertFalse(self.transport.keys)
        self.grant()
        self.transport.fail_key = (0xFF09, 1)
        self.remote.execute(action, lambda error: done.append(error))
        self.assertIsNotNone(done[-1])
        self.assertIn(("/session", 0xFFE1, 0), self.transport.keys)
        self.assertIn(("/session", 0xFF09, 0), self.transport.keys)

    def test_unicode_and_fixed_command_keys(self):
        self.assertEqual(keysym("a"), ord("a"))
        self.assertEqual(keysym("é"), 233)
        self.assertEqual(keysym("λ"), 0x010003BB)
        self.grant()
        done = []
        self.remote.execute(
            PendingAction("a", ActionKind.TEXT, "aλ", Risk.NORMAL, 0, 30), done.append
        )
        self.assertEqual(
            [x[1:] for x in self.transport.keys],
            [(97, 1), (97, 0), (0x010003BB, 1), (0x010003BB, 0)],
        )
        self.assertEqual(done, [None])

    def test_custom_reviewed_chord_executes_and_portal_rejects_malformed_plans(self):
        from dataclasses import replace

        self.grant()
        action = PendingAction(
            "a",
            ActionKind.COMMAND,
            "custom-save",
            Risk.HIGH,
            0,
            30,
            key_chord="Ctrl+Super+S",
        )
        done = []
        self.remote.execute(action, done.append)
        self.assertEqual(done, [None])
        self.assertEqual(
            [entry[1:] for entry in self.transport.keys],
            [
                (0xFFE3, 1),
                (0xFFEB, 1),
                (ord("s"), 1),
                (ord("s"), 0),
                (0xFFEB, 0),
                (0xFFE3, 0),
            ],
        )
        for chord in ("Ctrl+S;rm", "Ctrl+Ctrl+S", "XF86AudioMute", "Ctrl+S,Ctrl+T"):
            self.transport.keys.clear()
            self.remote.execute(replace(action, key_chord=chord), done.append)
            self.assertIsNotNone(done[-1])
            self.assertFalse(self.transport.keys)

    def test_custom_chord_releases_every_pressed_key_on_failure_and_cancellation(self):
        self.grant()
        action = PendingAction(
            "a", ActionKind.COMMAND, "save", Risk.HIGH, 0, 30, key_chord="Ctrl+Alt+S"
        )
        self.transport.fail_key = (ord("s"), 1)
        done = []
        self.remote.execute(action, done.append)
        self.assertIsNotNone(done[-1])
        self.assertEqual(
            [entry[1:] for entry in self.transport.keys][-3:],
            [(ord("s"), 0), (0xFFE9, 0), (0xFFE3, 0)],
        )
        self.transport.keys.clear()
        self.transport.fail_key = None
        original = self.transport.notify_key

        def cancel_after_press(session, symbol, state):
            original(session, symbol, state)
            if state == 1:
                self.remote.cancel_input()

        self.transport.notify_key = cancel_after_press
        self.remote.execute(action, done.append)
        self.assertIsNotNone(done[-1])
        self.assertEqual(
            [entry[1:] for entry in self.transport.keys], [(0xFFE3, 1), (0xFFE3, 0)]
        )

    def test_owner_loss_revokes_completed_grant_and_notifies_once(self):
        closed = []
        self.remote.on_closed = lambda closed=closed: closed.append(True)
        self.grant()
        self.transport.lose_owner()
        self.assertFalse(self.remote.granted)
        self.assertEqual(closed, [True])
        self.assertEqual(self.transport.signals, {})
        self.assertEqual(len(self.transport.requests), 3)

    def test_owner_loss_during_each_stage_rejects_late_grant(self):
        for stage in range(3):
            with self.subTest(stage=stage):
                self.setUp()
                closed = []
                self.remote.on_closed = lambda closed=closed: closed.append(True)
                self.remote.connect(lambda *args: self.events.append(args))
                if stage > 0:
                    self.transport.reply({"session_handle": "/session"})
                if stage > 1:
                    self.transport.reply()
                pending = self.transport.requests[-1]
                self.transport.lose_owner()
                pending[5](0, {"session_handle": "/session", "devices": 1}, None)
                self.assertFalse(self.remote.granted)
                self.assertEqual(closed, [True])
                self.assertFalse(self.transport.signals)
                self.assertEqual(len(self.transport.requests), stage + 1)

    def test_old_owner_callback_cannot_revoke_a_new_explicit_session(self):
        self.grant()
        stale = next(
            v[3] for v in self.transport.signals.values() if v[1] == "owner_lost"
        )
        self.grant()
        stale()
        self.assertTrue(self.remote.granted)
        self.remote.close()
        self.assertFalse(self.transport.signals)

    def test_session_closed_revokes_permission(self):
        self.grant()
        next(v[3] for v in self.transport.signals.values() if v[1] == "Closed")(())
        self.assertFalse(self.remote.granted)


class ShortcutTests(unittest.TestCase):
    def test_owner_loss_clears_completed_or_pending_shortcuts(self):
        for stage in range(3):
            with self.subTest(stage=stage):
                wire, closed = FakeTransport(), []
                shortcuts = GlobalShortcuts(
                    wire,
                    lambda *_: None,
                    on_closed=lambda closed=closed: closed.append(True),
                )
                shortcuts.connect(lambda *_: None)
                if stage > 0:
                    wire.reply({"session_handle": "/shortcuts"})
                if stage > 1:
                    wire.reply({"shortcuts": [("confirm", {})]})
                pending = wire.requests[-1]
                wire.lose_owner()
                pending[5](
                    0,
                    {"session_handle": "/shortcuts", "shortcuts": [("confirm", {})]},
                    None,
                )
                self.assertEqual(shortcuts.bindings, {})
                self.assertEqual(closed, [True])
                self.assertFalse(wire.signals)
                self.assertEqual(len(wire.requests), min(stage + 1, 2))

    def test_granted_subset_repeat_dedup_and_confirm_on_release(self):
        wire = FakeTransport()
        events = []
        shortcuts = GlobalShortcuts(
            wire, lambda name, active: events.append((name, active))
        )
        shortcuts.connect(lambda *args: None)
        wire.reply({"session_handle": "/shortcuts"})
        wire.reply({"shortcuts": [("confirm", {"trigger_description": "Ctrl+Y"})]})
        self.assertEqual(shortcuts.bindings, {"confirm": "Ctrl+Y"})
        signal = lambda name, session, key: next(
            v[3] for v in wire.signals.values() if v[1] == name
        )((session, key, 1, {}))
        signal("Activated", "/other", "confirm")
        signal("Deactivated", "/shortcuts", "confirm")
        signal("Activated", "/shortcuts", "confirm")
        signal("Activated", "/shortcuts", "confirm")
        self.assertEqual(events, [])
        signal("Deactivated", "/shortcuts", "confirm")
        signal("Deactivated", "/shortcuts", "confirm")
        self.assertEqual(events, [("confirm", False)])
        shortcuts.close()
        self.assertFalse(wire.signals)
        self.assertIn("/shortcuts", wire.closed)

    def ready_shortcuts(self):
        wire, events, changed = FakeTransport(), [], []
        shortcuts = GlobalShortcuts(wire, lambda *args: events.append(args))
        shortcuts.on_changed = changed.append
        shortcuts.connect(lambda *_: None)
        wire.reply({"session_handle": "/s"})
        wire.reply(
            {
                "shortcuts": [
                    ("hold_to_talk", {"trigger_description": "Old talk"}),
                    ("confirm", {"trigger_description": "Old confirm"}),
                ]
            }
        )
        return wire, shortcuts, events, changed

    def emit(self, wire, signal, values):
        callbacks = [entry[3] for entry in wire.signals.values() if entry[1] == signal]
        self.assertEqual(len(callbacks), 1, f"Missing {signal} subscription")
        callbacks[0](values)
        return callbacks[0]

    def test_shortcuts_changed_merges_partial_bindings_and_notifies(self):
        wire, shortcuts, events, changed = self.ready_shortcuts()
        self.emit(
            wire,
            "ShortcutsChanged",
            ("/s", [("confirm", {"trigger_description": "New confirm"})]),
        )
        self.assertEqual(
            shortcuts.bindings, {"hold_to_talk": "Old talk", "confirm": "New confirm"}
        )
        self.assertEqual(changed, [frozenset({"confirm"})])
        self.assertEqual(events, [])

    def test_changed_held_keys_require_release_and_repress_without_synthetic_confirm(
        self,
    ):
        wire, shortcuts, events, changed = self.ready_shortcuts()
        for key in ("hold_to_talk", "confirm"):
            self.emit(wire, "Activated", ("/s", key, 0, {}))
        self.emit(
            wire,
            "ShortcutsChanged",
            ("/s", [("confirm", {"trigger_description": "New confirm"})]),
        )
        for key in ("hold_to_talk", "confirm"):
            self.emit(wire, "Activated", ("/s", key, 0, {}))  # Repeat while still held.
            self.emit(wire, "Deactivated", ("/s", key, 0, {}))
        self.assertEqual(events, [("hold_to_talk", True)])
        self.emit(wire, "Activated", ("/s", "confirm", 0, {}))
        self.emit(wire, "Deactivated", ("/s", "confirm", 0, {}))
        self.assertEqual(events[-1], ("confirm", False))
        self.assertEqual(len(changed), 1)
        shortcuts.close()
        self.assertFalse(wire.signals)

    def test_changed_ignores_malformed_unknown_stale_and_pregrant_events(self):
        wire, shortcuts, events, changed = self.ready_shortcuts()
        before = dict(shortcuts.bindings)
        for values in (
            (),
            None,
            ("/s",),
            ("/other", [("confirm", {})]),
            ("/s", None),
            (
                "/s",
                [
                    None,
                    (),
                    ([], {}),
                    ("unknown", {}),
                    ("confirm", None),
                    ("confirm", {"trigger_description": 2}),
                ],
            ),
        ):
            self.emit(wire, "ShortcutsChanged", values)
        self.assertEqual(shortcuts.bindings, before)
        self.assertEqual(changed, [])
        stale = self.emit(wire, "ShortcutsChanged", ("/other", []))
        old_press = next(
            entry[3] for entry in wire.signals.values() if entry[1] == "Activated"
        )
        shortcuts.connect(lambda *_: None)
        wire.reply({"session_handle": "/s"})
        self.emit(wire, "ShortcutsChanged", ("/s", [("confirm", {})]))
        self.assertEqual(shortcuts.bindings, {})
        wire.reply(
            {"shortcuts": [("confirm", {"trigger_description": "Explicit new grant"})]}
        )
        stale(("/s", [("confirm", {"trigger_description": "Stale"})]))
        old_press(("/s", "confirm", 0, {}))
        self.emit(wire, "Deactivated", ("/s", "confirm", 0, {}))
        self.assertEqual(shortcuts.bindings, {"confirm": "Explicit new grant"})
        self.assertEqual(events, [])
        self.assertEqual(changed, [])

    def test_shortcut_input_ignores_malformed_payload(self):
        wire, _shortcuts, events, _changed = self.ready_shortcuts()
        for values in ((), None, ("/s",), ("/s", []), ("/s", {})):
            self.emit(wire, "Activated", values)
        self.assertEqual(events, [])

    def test_ptt_press_release_only_for_bound_shortcuts(self):
        wire = FakeTransport()
        events = []
        shortcuts = GlobalShortcuts(wire, lambda *args: events.append(args))
        shortcuts.connect(lambda *args: None)
        wire.reply({"session_handle": "/s"})
        wire.reply({"shortcuts": [("hold_to_talk", {})]})
        for name in ("Activated", "Activated", "Deactivated", "Deactivated"):
            next(v[3] for v in wire.signals.values() if v[1] == name)(
                ("/s", "hold_to_talk", 0, {})
            )
        self.assertEqual(events, [("hold_to_talk", True), ("hold_to_talk", False)])


class GioWireTests(unittest.TestCase):
    def test_owner_subscription_ignores_initial_activation_and_other_names(self):
        from gi.repository import GLib

        from wayland_voice_control.gio_transport import GioWire
        from wayland_voice_control.transport import DESTINATION

        class Connection:
            def get_unique_name(self):
                return ":1.42"

            def signal_subscribe(self, *args):
                self.args = args
                return 19

        connection, lost = Connection(), []
        wire = GioWire(connection)
        self.assertEqual(wire.subscribe_owner_lost(lambda: lost.append(True)), 19)
        args = connection.args
        self.assertEqual(
            args[:5],
            (
                "org.freedesktop.DBus",
                "org.freedesktop.DBus",
                "NameOwnerChanged",
                "/org/freedesktop/DBus",
                DESTINATION,
            ),
        )
        for name, before, after in [
            (DESTINATION, "", ":1.1"),
            ("other", ":1.1", ""),
            (DESTINATION, ":1.1", ":1.1"),
        ]:
            args[6](
                None,
                None,
                None,
                None,
                None,
                GLib.Variant("(sss)", (name, before, after)),
            )
        self.assertEqual(lost, [])
        for after in ("", ":1.2"):
            args[6](
                None,
                None,
                None,
                None,
                None,
                GLib.Variant("(sss)", (DESTINATION, ":1.1", after)),
            )
        self.assertEqual(lost, [True, True])

    def test_real_variants_for_options_shortcuts_and_keys(self):
        from gi.repository import Gio, GLib

        from wayland_voice_control.gio_transport import GioWire

        class Connection:
            def get_unique_name(self):
                return ":1.42"

            def call(self, *args):
                self.call_args = args

            def call_sync(self, *args):
                self.sync_args = args
                return GLib.Variant("()", ())

        connection = Connection()
        wire = GioWire(connection)
        wire.call(
            "remote",
            "SelectDevices",
            "/desktop",
            "(oa{sv})",
            ("/session", {"types": 1, "persist_mode": 0}),
            lambda *_: None,
        )
        value = connection.call_args[4]
        self.assertEqual(value.get_type_string(), "(oa{sv})")
        self.assertEqual(value.unpack(), ("/session", {"types": 1, "persist_mode": 0}))
        wire.call(
            "shortcuts",
            "BindShortcuts",
            "/desktop",
            "(oa(sa{sv})sa{sv})",
            (
                "/s",
                [
                    (
                        "confirm",
                        {"description": "Confirm", "preferred_trigger": "<Control>Y"},
                    )
                ],
                "",
                {},
            ),
            lambda *_: None,
        )
        self.assertEqual(connection.call_args[4].unpack()[1][0][0], "confirm")
        wire.notify_key("/session", 97, 1)
        self.assertEqual(connection.sync_args[6], Gio.DBusCallFlags.NO_AUTO_START)
        wire.call("session", "Close", "/s", "()", (), lambda *_: None)
        self.assertEqual(connection.call_args[6], Gio.DBusCallFlags.NO_AUTO_START)
        self.assertEqual(
            connection.sync_args[2:5],
            (
                "org.freedesktop.portal.RemoteDesktop",
                "NotifyKeyboardKeysym",
                GLib.Variant("(oa{sv}iu)", ("/session", {}, 97, 1)),
            ),
        )


class AdditionalProtocolTests(unittest.TestCase):
    def test_cancel_closes_predicted_session_even_after_response_unsubscribe(self):
        wire = FakeWire()
        transport = RequestTransport(wire, token_factory=lambda: "request")
        remote = RemoteDesktop(transport, dispatch=lambda f: f())
        remote.connect(lambda *_: None)
        session_token = wire.events[1][2][-1]["session_handle_token"]
        remote.close()
        expected = "/org/freedesktop/portal/desktop/session/1_25/" + session_token
        self.assertTrue(any(event[:2] == ("Close", expected) for event in wire.events))

    def test_shortcut_preferred_triggers_use_xdg_syntax(self):
        wire = FakeTransport()
        shortcuts = GlobalShortcuts(wire, lambda *_: None)
        shortcuts.connect(lambda *_: None)
        wire.reply({"session_handle": "/s"})
        bindings = dict(wire.requests[-1][3][1])
        self.assertEqual(
            bindings["hold_to_talk"]["preferred_trigger"], "CTRL+ALT+space"
        )

    def test_cancellation_between_keys_releases_and_sends_no_remaining_keys(self):
        wire = FakeTransport()
        jobs, results = [], []
        remote = RemoteDesktop(wire, dispatch=lambda f: f(), run_worker=jobs.append)
        remote.connect(lambda *_: None)
        wire.reply({"session_handle": "/s"})
        wire.reply()
        wire.reply({"devices": 1})
        original = wire.notify_key

        def send(session, symbol, state):
            original(session, symbol, state)
            if state == 1:
                remote.cancel_input()

        wire.notify_key = send
        remote.execute(
            PendingAction("a", ActionKind.TEXT, "abc", Risk.NORMAL, 0, 30),
            results.append,
        )
        jobs.pop()()
        self.assertEqual(wire.keys, [("/s", 97, 1), ("/s", 97, 0)])
        self.assertIsNotNone(results[0])

    def test_response_cannot_grant_before_method_handle_is_verified(self):
        wire = FakeWire()
        results = []
        RequestTransport(wire, token_factory=lambda: "abc").request(
            "remote", "Start", "(a{sv})", (), {}, lambda *args: results.append(args)
        )
        wire.callback((0, {"devices": 1}))
        self.assertEqual(results, [])
        wire.method_done(("/unexpected",), None)
        self.assertEqual(len(results), 1)
        self.assertIsNotNone(results[0][2])
