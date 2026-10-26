"""Resident lifecycle and real session-bus protocol, with fake live boundaries."""

import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.test_controller import Audio, Remote, Scheduler
from wayland_voice_control.controller import Controller, PracticeInput
from wayland_voice_control.domain import State


class ApplicationIdentityTests(unittest.TestCase):
    def test_explicit_settings_are_deterministically_isolated_from_default(self):
        from wayland_voice_control import app

        self.assertTrue(
            hasattr(app, "application_identity"),
            "isolated application identity is missing",
        )
        application_identity = app.application_identity
        default = application_identity()
        explicit = application_identity(Path("/tmp/private/settings.db"))
        self.assertEqual(
            default,
            (
                "io.github.wayland_voice_control",
                "/io/github/wayland_voice_control/Controls",
            ),
        )
        self.assertNotEqual(default[0], explicit[0])
        self.assertNotEqual(default[1], explicit[1])
        self.assertEqual(
            explicit, application_identity(Path("/tmp/private/./settings.db"))
        )


@unittest.skipUnless(os.environ.get("WVC_GTK_TESTS") == "1", "GTK display test opt-in")
class ResidentApplicationTests(unittest.TestCase):
    def setUp(self):
        import gi

        gi.require_version("Gtk", "4.0")
        gi.require_version("Adw", "1")
        from gi.repository import Gio, GLib

        from wayland_voice_control import app

        self.assertTrue(
            hasattr(app, "create_application"),
            "testable resident application factory is missing",
        )
        create_application = app.create_application
        self.Gio, self.GLib = Gio, GLib
        self.directory = tempfile.TemporaryDirectory()
        self.scheduler = Scheduler()
        self.created = []

        def factory(*, practice, store):
            self.created.append(practice)
            return Controller(
                settings=store.load(),
                store=store,
                remote=PracticeInput() if practice else Remote(),
                audio=None if practice else Audio(),
                practice=practice,
                schedule=self.scheduler.schedule,
                dispatch=lambda f: f(),
                clock=lambda: self.scheduler.now,
            )

        self.app = create_application(
            settings_path=Path(self.directory.name) / "private/settings.db",
            controller_factory=factory,
        )
        self.app.register(None)
        self.client = Gio.DBusConnection.new_for_address_sync(
            os.environ["DBUS_SESSION_BUS_ADDRESS"],
            Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT
            | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION,
            None,
            None,
        )

    def tearDown(self):
        if hasattr(self, "app"):
            self.app.quit_controls()
            self.app.do_shutdown()
            self.app.window.destroy()
            self.client.close_sync(None)
            self.directory.cleanup()

    def spin(self, predicate):
        deadline = time.monotonic() + 3
        while not predicate():
            if time.monotonic() > deadline:
                self.fail("main-loop operation timed out")
            self.GLib.MainContext.default().iteration(False)

    def call(self, name, parameters=None, *, bus_name=None, path=None):
        received = []

        def done(client, result):
            try:
                received.append(client.call_finish(result))
            except self.GLib.Error as error:
                received.append(error)

        self.client.call(
            bus_name or self.app.get_application_id(),
            path or self.app.controls_path,
            "io.github.wayland_voice_control.Controls1",
            name,
            parameters,
            None,
            self.Gio.DBusCallFlags.NONE,
            2000,
            None,
            done,
        )
        self.spin(lambda: received)
        if isinstance(received[0], Exception):
            raise received[0]
        return received[0].unpack()[0]

    def ready_live(self):
        window = self.app.window
        window.practice_switch.set_active(False)
        window.model_path.set_text("/private/model")
        window.mic_consent.set_active(True)
        window.persist_settings()
        controller = window.controller
        controller.prepare_model()
        controller.connect()
        controller.remote.grant()
        return controller

    def test_ordinary_launch_background_off_and_cold_start_practice(self):
        self.assertEqual(self.created, [True])
        self.assertFalse(self.app.window.keep_available.get_active())
        self.assertFalse(self.call("StartRecording"))
        self.assertFalse(self.app.window.get_visible())
        self.assertTrue(self.call("Show"))
        self.assertTrue(self.app.window.get_visible())

    def test_status_is_allowlisted_and_typed_and_rejects_arguments(self):
        status = self.call("GetStatus")
        self.assertEqual(
            set(status),
            {
                "version",
                "practice",
                "state",
                "microphone",
                "model",
                "can_start",
                "pending_review",
                "window_visible",
                "background",
            },
        )
        self.assertEqual(status["version"], 1)
        self.assertTrue(status["practice"])
        self.assertFalse(status["can_start"])
        self.assertEqual(self.app.get_status()["version"].get_type_string(), "u")
        self.app.window.controller._activity = "private draft"
        self.app.window.controller._model_readiness = "/private/model"
        sanitized = self.call("GetStatus")
        self.assertEqual(sanitized["microphone"], "idle")
        self.assertEqual(sanitized["model"], "error")
        self.assertNotIn("private", str(sanitized))
        with self.assertRaises(self.GLib.Error):
            self.call(
                "StartRecording", self.GLib.Variant("(s)", ("unreviewed content",))
            )
        with self.assertRaises(self.GLib.Error):
            self.call("Confirm")

    def test_ipc_capture_survives_inactive_window_and_opens_final_review(self):
        controller = self.ready_live()
        self.assertTrue(self.call("StartRecording"))
        self.assertTrue(self.app.window.keep_available.get_active())
        self.assertFalse(self.call("StartRecording"))
        self.app.window._active_changed()
        self.assertEqual(controller.snapshot.state, State.RECORDING)
        self.assertEqual(
            controller.audio.callbacks["limit"],
            controller.settings.capture_limit_seconds,
        )
        controller.audio.callbacks["on_activity"]("recording")
        controller.audio.callbacks["on_draft"]("secret provisional")
        self.assertNotIn("secret", str(self.call("GetStatus")))
        self.assertTrue(self.call("FinishRecording"))
        self.assertFalse(self.call("FinishRecording"))
        controller.audio.callbacks["on_result"]("secret final")
        self.assertTrue(self.app.window.get_visible())
        self.assertTrue(self.call("GetStatus")["pending_review"])
        self.assertNotIn("secret", str(self.call("GetStatus")))
        self.assertEqual(controller.remote.actions, [])

    def test_hidden_review_opens_voice_page_without_notifications_service_activation(
        self,
    ):
        controller = self.ready_live()
        self.app.window.stack.set_visible_child_name("setup")
        self.app.set_background(True)
        with patch.object(self.app, "send_notification") as notify:
            self.assertTrue(self.call("StartRecording"))
            controller.audio.callbacks["on_result"]("private review")
            self.assertEqual(self.app.window.stack.get_visible_child_name(), "voice")
            drained = []
            self.GLib.timeout_add(30, lambda: drained.append(True) and False)
            self.spin(lambda: drained)
            notify.assert_not_called()

    def test_review_notification_contains_only_generic_copy(self):
        controller = self.ready_live()
        self.app.set_background(True)
        self.client.call_sync(
            "org.freedesktop.DBus",
            "/org/freedesktop/DBus",
            "org.freedesktop.DBus",
            "RequestName",
            self.GLib.Variant("(su)", ("org.freedesktop.Notifications", 0)),
            None,
            self.Gio.DBusCallFlags.NONE,
            2000,
            None,
        )
        try:
            with (
                patch.object(self.Gio.Notification, "new") as make,
                patch.object(self.app, "send_notification") as send,
            ):
                self.call("StartRecording")
                controller.audio.callbacks["on_result"](
                    "private words never in notifications"
                )
                self.spin(lambda: send.called)
                make.assert_called_once_with("Voice action ready for review")
                make.return_value.set_body.assert_called_once_with(
                    "Open Wayland Voice Control to review the action."
                )
        finally:
            self.client.call_sync(
                "org.freedesktop.DBus",
                "/org/freedesktop/DBus",
                "org.freedesktop.DBus",
                "ReleaseName",
                self.GLib.Variant("(s)", ("org.freedesktop.Notifications",)),
                None,
                self.Gio.DBusCallFlags.NONE,
                2000,
                None,
            )

    def test_hidden_close_cancels_review_and_capture_but_retains_grants(self):
        controller = self.ready_live()
        self.app.set_background(True)
        self.app.show_controls()
        self.call("StartRecording")
        self.assertTrue(self.app.window._close())
        self.assertFalse(self.app.window.get_visible())
        self.assertEqual(controller.snapshot.state, State.IDLE)
        self.assertTrue(controller.remote.granted)
        self.app.show_controls()
        self.assertIs(self.app.window.controller, controller)
        self.app.window._close()
        self.assertFalse(self.app.window.get_visible())
        controller.shortcut_event("show_controls", True)
        self.assertFalse(self.app.window.get_visible())
        controller.shortcut_event("show_controls", False)
        self.assertTrue(self.app.window.get_visible())
        self.call("StartRecording")
        controller.audio.callbacks["on_result"]("review")
        self.app.window._close()
        self.assertIsNone(controller.snapshot.pending)
        self.assertTrue(controller.remote.granted)

    def test_dirty_setup_blocks_ipc_and_stop_quit_revoke(self):
        controller = self.ready_live()
        self.app.window.model_path.set_text("/changed")
        self.assertFalse(self.call("GetStatus")["can_start"])
        self.assertFalse(self.call("StartRecording"))
        self.assertFalse(self.app.window.keep_available.get_active())
        self.assertTrue(self.call("Stop"))
        self.assertFalse(controller.remote.granted)
        self.assertTrue(self.call("Quit"))
        self.assertTrue(self.app.window._closed)
        self.app.quit_controls()
        closed = controller.remote.closed
        self.app.quit_controls()
        self.assertEqual(controller.remote.closed, closed)

    def test_background_command_holds_loop_until_quit_and_second_launch_presents(self):
        observed = []
        processes = []

        def check_resident():
            observed.append(
                (
                    self.app.window.get_visible(),
                    self.app.window.keep_available.get_active(),
                )
            )
            processes.append(
                subprocess.Popen(
                    [
                        sys.executable,
                        "-c",
                        (
                            "import sys; from wayland_voice_control.app import create_application; "
                            "app = create_application(settings_path=sys.argv[1]); "
                            'raise SystemExit(app.run(["secondary"]))'
                        ),
                        str(self.app.window.store.path),
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
            )
            return False

        def finish_when_presented():
            if not processes or processes[0].poll() is None:
                return True
            observed.append(self.app.window.get_visible())
            self.call("Quit")
            return False

        self.GLib.timeout_add(20, check_resident)
        finish = self.GLib.timeout_add(20, finish_when_presented)
        fallback = self.GLib.timeout_add(
            5000, lambda: self.app.quit_controls() and False
        )
        result = self.app.run(["test-resident", "--background"])
        self.GLib.source_remove(fallback)
        if processes and processes[0].poll() is None:
            processes[0].kill()
            self.GLib.source_remove(finish)
        _stdout, stderr = processes[0].communicate(timeout=2)
        self.assertEqual(processes[0].returncode, 0, stderr.decode())
        self.assertEqual(result, 0)
        self.assertEqual(observed, [(False, True), True])
        self.assertEqual(self.created, [True])
        self.assertTrue(self.app._cleaned)
        self.assertIsNone(self.app._registration)

    def test_cold_background_subprocess_replies_to_quit_before_exiting(self):
        from wayland_voice_control.app import application_identity

        settings_path = Path(self.directory.name) / "cold/settings.db"
        bus_name, path = application_identity(settings_path)
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "wayland_voice_control",
                "gui",
                "--background",
                "--settings",
                str(settings_path),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        status = []

        def available():
            try:
                status.append(self.call("GetStatus", bus_name=bus_name, path=path))
            except self.GLib.Error:
                return False
            return True

        try:
            self.spin(available)
            self.assertTrue(status[-1]["practice"])
            self.assertTrue(status[-1]["background"])
            self.assertFalse(status[-1]["window_visible"])
            self.assertTrue(self.call("Quit", bus_name=bus_name, path=path))
            _stdout, stderr = process.communicate(timeout=3)
            self.assertEqual(process.returncode, 0, stderr.decode())
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=2)

    def test_normal_close_shuts_down_and_quit_button_is_explicit(self):
        controller = self.ready_live()
        self.app.show_controls()
        self.assertEqual(self.app.window.quit_button.get_child().get_text(), "Quit")
        self.assertFalse(self.app.window.quit_button.get_child().get_wrap())
        self.assertGreaterEqual(self.app.window.quit_button.get_size_request()[0], 64)
        self.assertGreaterEqual(
            self.app.window.keep_available.get_size_request()[1], 44
        )
        self.assertFalse(self.app.window._close())
        self.assertTrue(self.app.window._closed)
        self.assertFalse(controller.remote.granted)

    def test_background_relaunch_preserves_visible_window_and_pending_review(self):
        self.app.show_controls()
        self.app.window.review_practice()
        pending = self.app.window.controller.snapshot.pending

        class Command:
            def get_arguments(self):
                return ["test", "--background"]

        self.assertEqual(self.app.do_command_line(Command()), 0)
        self.assertTrue(self.app.window.get_visible())
        self.assertIs(self.app.window.controller.snapshot.pending, pending)

    def test_status_signal_tracks_controller_replacement_and_visibility(self):
        signals = []
        token = self.client.signal_subscribe(
            self.app.get_application_id(),
            "io.github.wayland_voice_control.Controls1",
            "StatusChanged",
            self.app.controls_path,
            None,
            self.Gio.DBusSignalFlags.NONE,
            lambda *args: signals.append(args[-1].unpack()[0]),
        )
        try:
            self.ready_live()
            self.app.show_controls()
            self.spin(
                lambda: any(
                    not value["practice"] and value["window_visible"]
                    for value in signals
                )
            )
            self.assertTrue(self.call("Cancel"))
        finally:
            self.client.signal_unsubscribe(token)
