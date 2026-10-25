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
        token = len(self.signals) + 1
        self.signals[token] = (interface, signal, path, callback)
        return token

    def unsubscribe(self, token):
        self.signals.pop(token, None)

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

    def subscribe(self, interface, signal, path, callback):
        self.events.append(("subscribe", path))
        self.callback = callback
        return 7

    def unsubscribe(self, token):
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

    def test_session_closed_revokes_permission(self):
        self.grant()
        next(iter(self.transport.signals.values()))[3](())
        self.assertFalse(self.remote.granted)


class ShortcutTests(unittest.TestCase):
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
    def test_real_variants_for_options_shortcuts_and_keys(self):
        from gi.repository import GLib

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
