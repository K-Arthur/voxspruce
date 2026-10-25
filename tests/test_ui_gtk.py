"""Run explicitly under dbus-run-session / Xvfb; pure CI need not have GTK."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.test_controller import Audio, Remote, Scheduler
from wayland_voice_control.controller import Controller, PracticeInput
from wayland_voice_control.domain import Mode, State
from wayland_voice_control.storage import SettingsStore


@unittest.skipUnless(os.environ.get("WVC_GTK_TESTS") == "1", "GTK display test opt-in")
class NativeWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import gi

        gi.require_version("Gtk", "4.0")
        gi.require_version("Adw", "1")
        from gi.repository import Adw, Gtk

        Gtk.init()
        Adw.init()

    def setUp(self):
        from wayland_voice_control.window import VoiceWindow

        self.directory = tempfile.TemporaryDirectory()
        self.store = SettingsStore(
            Path(self.directory.name) / "private" / "settings.db"
        )
        self.scheduler = Scheduler()
        self.created = []

        def factory(*, practice, store):
            self.created.append(practice)
            controller = Controller(
                settings=store.load(),
                store=store,
                remote=PracticeInput() if practice else Remote(),
                audio=None if practice else Audio(),
                practice=practice,
                schedule=self.scheduler.schedule,
                dispatch=lambda f: f(),
                clock=lambda: self.scheduler.now,
            )
            return controller

        self.window = VoiceWindow(store=self.store, controller_factory=factory)

    def tearDown(self):
        self.window.shutdown()
        self.window.destroy()
        self.directory.cleanup()

    def practice_review(self, text="hello", commands=False):
        self.window.command_mode.set_active(commands)
        self.window.practice_entry.set_text(text)
        self.window.practice_review.emit("clicked")

    def test_launch_practice_never_constructs_live_and_no_capture(self):
        self.assertEqual(self.created, [True])
        self.assertTrue(self.window.controller.practice)
        self.assertIsNone(self.window.controller.audio)
        self.assertFalse(self.window.hold_button.get_sensitive())
        self.assertFalse(self.window.model_prepare.get_sensitive())
        self.assertIn("Practice", self.window.mode_status.get_text())

    def test_edit_revokes_pending_before_buffer_is_editable(self):
        self.practice_review()
        old = self.window.controller.snapshot.pending.id
        self.assertFalse(self.window.editor.get_editable())
        self.window.edit_button.emit("clicked")
        self.assertIsNone(self.window.controller.snapshot.pending)
        self.assertEqual(self.window.controller.snapshot.state, State.EDITING)
        self.assertTrue(self.window.editor.get_editable())
        self.assertFalse(self.window.confirm_button.get_sensitive())
        self.window.editor.get_buffer().set_text("new literal")
        self.assertFalse(self.window.controller.confirm(old))
        self.window.rereview_button.emit("clicked")
        self.assertNotEqual(old, self.window.controller.snapshot.pending.id)
        self.assertEqual(self.window.controller.snapshot.pending.payload, "new literal")
        self.assertFalse(self.window.editor.get_editable())

    def test_high_risk_two_controls_countdown_and_practice_output(self):
        self.practice_review("press enter", commands=True)
        self.assertIn("Return", self.window.review_details.get_text())
        self.window.confirm_button.emit("clicked")
        self.assertEqual(
            self.window.controller.snapshot.state, State.AWAITING_SECOND_CONFIRMATION
        )
        self.assertTrue(self.window.second_button.get_visible())
        self.assertFalse(self.window.confirm_button.get_sensitive())
        self.window.second_button.emit("clicked")
        self.assertIn("destination", self.window.countdown.get_text())
        self.scheduler.advance(3)
        self.assertIn("Return", self.window.practice_output.get_text())
        self.assertIn("simulated", self.window.practice_output.get_text())

    def test_stop_and_escape_discard_edit_and_pending(self):
        self.practice_review()
        self.window.stop_button.emit("clicked")
        self.assertIsNone(self.window.controller.snapshot.pending)
        self.assertTrue(self.window.stop_button.get_sensitive())
        self.practice_review()
        self.window.cancel_action()
        self.assertIsNone(self.window.controller.snapshot.pending)

    def test_mode_switch_stops_old_controller_and_live_needs_setup(self):
        old = self.window.controller
        self.practice_review()
        self.window.practice_switch.set_active(False)
        self.assertFalse(old.remote.granted)
        self.assertIsNone(old.snapshot.pending)
        self.assertEqual(self.created, [True, False])
        self.assertFalse(self.window.hold_button.get_sensitive())
        self.window.hold_begin()
        self.assertEqual(self.window.controller.audio.callbacks, {})
        self.assertIn("ready", self.window.readiness.get_text().lower())
        self.window.practice_switch.set_active(True)
        self.assertEqual(self.created, [True, False, True])

    def test_settings_save_reset_are_explicit_and_revoke(self):
        self.window.model_path.set_text("/offline/model")
        self.window.mic_consent.set_active(True)
        self.window.focus_delay.set_value(5)
        self.window.save_settings.emit("clicked")
        self.assertTrue(self.store.load().microphone_consent)
        self.assertEqual(self.store.load().model_path, "/offline/model")
        self.assertEqual(self.store.load().focus_delay_seconds, 5)
        self.window.reset_settings.emit("clicked")
        self.assertFalse(self.store.load().microphone_consent)
        self.assertEqual(self.window.model_path.get_text(), "")

    def test_custom_manager_preview_save_disable_edit_delete_and_collision(self):
        self.window.custom_phrase.set_text("save document")
        self.window.custom_chord.set_text("ctrl+s")
        self.window.custom_description.set_text("Save current file")
        self.assertIn("Ctrl+S", self.window.custom_preview.get_text())
        self.window.custom_save.emit("clicked")
        item = self.window.controller.snapshot.custom_shortcuts[0]
        self.assertEqual(item.phrase, "save document")
        self.window.load_custom(item)
        self.window.custom_enabled.set_active(False)
        self.window.custom_save.emit("clicked")
        self.assertFalse(self.store.load_custom_shortcuts()[0].enabled)
        self.window.custom_new.emit("clicked")
        self.window.custom_phrase.set_text("copy")
        self.window.custom_chord.set_text("Ctrl+C")
        self.window.custom_save.emit("clicked")
        self.assertIn("unique", self.window.custom_error.get_text())
        self.assertEqual(len(self.store.load_custom_shortcuts()), 1)
        self.window.load_custom(self.store.load_custom_shortcuts()[0])
        self.window.custom_delete.emit("clicked")
        self.assertEqual(self.store.load_custom_shortcuts(), ())

    def test_live_errors_and_drafts_display_without_approval(self):
        self.window.practice_switch.set_active(False)
        controller = self.window.controller
        controller._model_readiness = "ready"
        controller.settings = __import__("dataclasses").replace(
            controller.settings, microphone_consent=True
        )
        controller._workflow.set_microphone_consent(True)
        controller.connect()
        controller.remote.grant()
        self.window.hold_begin()
        controller.audio.callbacks["on_activity"]("recording")
        controller.audio.callbacks["on_draft"]("provisional words")
        self.assertIn("provisional words", self.window.draft.get_text())
        self.assertIsNone(controller.snapshot.pending)
        self.window.hold_end()
        self.assertEqual(self.window.draft.get_text(), "")
        controller.audio.callbacks["on_error"]("Microphone unavailable.")
        self.assertIn("Microphone unavailable", self.window.status.get_text())
        self.assertFalse(self.window.confirm_button.get_sensitive())

    def test_readback_is_stopped_on_every_action_invalidation(self):
        import threading

        class Reader:
            def __init__(self):
                self.terminated = False
                self.finished = threading.Event()

            def communicate(self, *args, **kwargs):
                self.finished.wait(2)

            def terminate(self):
                self.terminated = True
                self.finished.set()

        for invalidate in (
            lambda: self.window.edit_button.emit("clicked"),
            lambda: self.window.controller.cancel(),  # includes global cancel
            lambda: self.window.save_settings.emit("clicked"),
            lambda: self.window.reset_settings.emit("clicked"),
            lambda: self.window.confirm_button.emit("clicked"),
            lambda: self.window.practice_switch.set_active(False),
        ):
            if not self.window.controller.practice:
                self.window.practice_switch.set_active(True)
            self.practice_review()
            reader = Reader()
            with (
                patch(
                    "wayland_voice_control.window.shutil.which",
                    return_value="/usr/bin/espeak-ng",
                ),
                patch(
                    "wayland_voice_control.window.subprocess.Popen", return_value=reader
                ) as spawn,
            ):
                self.window.read_back()
                self.assertIs(self.window._reader, reader)
                self.assertEqual(
                    spawn.call_args.args[0], ["/usr/bin/espeak-ng", "--stdin"]
                )
                invalidate()
                self.assertTrue(reader.terminated)
                self.assertIsNone(self.window._reader)

    def test_readback_spawn_failure_is_actionable_and_preserves_review(self):
        self.practice_review()
        identity = self.window.controller.snapshot.pending.id
        with (
            patch(
                "wayland_voice_control.window.shutil.which",
                return_value="/usr/bin/espeak-ng",
            ),
            patch(
                "wayland_voice_control.window.subprocess.Popen",
                side_effect=OSError("gone"),
            ),
        ):
            self.window.read_back()
        self.assertIn("espeak-ng", self.window.status.get_text())
        self.assertEqual(self.window.controller.snapshot.pending.id, identity)

    def test_hold_focus_loss_cancels_before_late_release(self):
        self.window.practice_switch.set_active(False)
        controller = self.window.controller
        controller._model_readiness = "ready"
        controller.settings = __import__("dataclasses").replace(
            controller.settings, microphone_consent=True
        )
        controller._workflow.set_microphone_consent(True)
        controller.connect()
        controller.remote.grant()
        self.window.hold_begin()
        self.assertTrue(self.window._held)
        self.window._hold_focus_changed()
        self.assertFalse(self.window._held)
        self.assertEqual(controller.snapshot.state, State.IDLE)
        self.window.hold_end()
        self.assertEqual(controller.snapshot.state, State.IDLE)

    def test_duration_cap_clears_indicator_but_latches_until_physical_release(self):
        self.window.practice_switch.set_active(False)
        controller = self.window.controller
        controller._model_readiness = "ready"
        controller.settings = __import__("dataclasses").replace(
            controller.settings, microphone_consent=True
        )
        controller._workflow.set_microphone_consent(True)
        controller.connect()
        controller.remote.grant()
        self.window.hold_begin()
        controller.audio.callbacks["on_activity"]("recording")
        self.assertIn("Recording", self.window.hold_button.get_label())
        controller.audio.callbacks["on_activity"]("processing")
        controller.audio.callbacks["on_result"]("after duration cap")
        self.assertNotIn("Recording", self.window.hold_button.get_label())
        self.window.hold_begin()  # key auto-repeat while the same key remains held
        self.assertEqual(controller.snapshot.state, State.REVIEWING)
        controller.cancel()
        self.window.hold_begin()  # cancelling a capped action still must not restart this hold
        self.assertEqual(controller.snapshot.state, State.IDLE)
        self.window.hold_end()
        self.window.hold_begin()
        self.assertEqual(controller.snapshot.state, State.RECORDING)
        self.window.hold_end()

    def test_inputs_have_programmatic_accessible_labels(self):
        from gi.repository import Gtk

        for widget in (
            self.window.model_path,
            self.window.mic_consent,
            self.window.focus_delay,
            self.window.capture_limit,
            self.window.review_lifetime,
            self.window.theme,
            self.window.custom_phrase,
            self.window.custom_chord,
            self.window.custom_description,
            self.window.custom_enabled,
            self.window.practice_entry,
        ):
            with self.subTest(widget=widget):
                self.assertTrue(
                    Gtk.test_accessible_has_property(
                        widget, Gtk.AccessibleProperty.LABEL
                    )
                )

    def test_long_custom_phrases_do_not_force_wide_buttons(self):
        from gi.repository import Gtk

        from wayland_voice_control.commands import CustomShortcut

        self.window.controller.add_custom_shortcut(
            CustomShortcut("long", "x" * 100, "Ctrl+S")
        )
        row = self.window.command_list.get_last_child().get_prev_sibling()
        edit = row.get_first_child().get_next_sibling()
        practice = edit.get_next_sibling()
        self.assertLessEqual(edit.measure(Gtk.Orientation.HORIZONTAL, -1).minimum, 300)
        self.assertLessEqual(
            practice.measure(Gtk.Orientation.HORIZONTAL, -1).minimum, 300
        )

    def test_all_views_are_attached_to_the_visible_native_window(self):
        self.assertIs(self.window.stack.get_root(), self.window)
        for name in ("voice", "commands", "setup"):
            child = self.window.stack.get_child_by_name(name)
            self.assertIs(child.get_root(), self.window)
        self.assertIs(self.window.practice_entry.get_root(), self.window)
        self.assertIs(self.window.model_path.get_root(), self.window)

    def test_real_space_release_after_duration_cap_allows_a_new_hold(self):
        import ctypes
        import ctypes.util

        from gi.repository import Gdk, GLib

        x11 = ctypes.CDLL(ctypes.util.find_library("X11"))
        xtst = ctypes.CDLL(ctypes.util.find_library("Xtst"))
        x11.XOpenDisplay.restype = ctypes.c_void_p
        x11.XKeysymToKeycode.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        x11.XKeysymToKeycode.restype = ctypes.c_uint
        x11.XFlush.argtypes = [ctypes.c_void_p]
        x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
        x11.XSetInputFocus.argtypes = [
            ctypes.c_void_p,
            ctypes.c_ulong,
            ctypes.c_int,
            ctypes.c_ulong,
        ]
        xtst.XTestFakeKeyEvent.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint,
            ctypes.c_int,
            ctypes.c_ulong,
        ]
        display = x11.XOpenDisplay(None)
        self.assertTrue(display)

        def pump():
            loop = GLib.MainLoop()
            GLib.timeout_add(80, lambda: loop.quit() or False)
            loop.run()

        self.window.practice_switch.set_active(False)
        controller = self.window.controller
        controller._model_readiness = "ready"
        controller.settings = __import__("dataclasses").replace(
            controller.settings, microphone_consent=True
        )
        controller._workflow.set_microphone_consent(True)
        controller.connect()
        controller.remote.grant()
        self.window.present()
        pump()
        x11.XSetInputFocus(display, self.window.get_surface().get_xid(), 1, 0)
        self.window.hold_button.grab_focus()
        code = x11.XKeysymToKeycode(display, Gdk.KEY_space)
        try:
            xtst.XTestFakeKeyEvent(display, code, True, 0)
            x11.XFlush(display)
            pump()
            self.assertTrue(self.window._held)
            controller.audio.callbacks["on_activity"]("processing")
            controller.audio.callbacks["on_result"]("duration cap reached")
            xtst.XTestFakeKeyEvent(display, code, False, 0)
            x11.XFlush(display)
            pump()
            self.assertFalse(self.window._hold_pressed)
            controller.cancel()
            self.window.hold_button.grab_focus()
            xtst.XTestFakeKeyEvent(display, code, True, 0)
            x11.XFlush(display)
            pump()
            self.assertTrue(self.window._held)
        finally:
            xtst.XTestFakeKeyEvent(display, code, False, 0)
            x11.XFlush(display)
            pump()
            x11.XCloseDisplay(display)

    def test_real_practice_factory_never_touches_live_constructor(self):
        from wayland_voice_control.ui_model import create_controller

        with patch(
            "wayland_voice_control.gio_transport.GioWire",
            side_effect=AssertionError("live"),
        ):
            practice = create_controller(practice=True, store=self.store)
            self.assertIsNone(practice.audio)
            practice.review_text("hello", Mode.DICTATION)
            self.assertIsNotNone(practice.snapshot.pending)
            practice.stop()


if __name__ == "__main__":
    unittest.main()
