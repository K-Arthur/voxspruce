import threading
import unittest
from dataclasses import replace

from tests.test_controller import Audio, Remote, Scheduler
from wayland_voice_control.commands import CustomShortcut
from wayland_voice_control.controller import Controller, PracticeInput
from wayland_voice_control.domain import DomainError, Mode, State
from wayland_voice_control.storage import Settings


class CustomControllerTests(unittest.TestCase):
    def setUp(self):
        self.remote, self.audio, self.scheduler = Remote(), Audio(), Scheduler()
        self.controller = Controller(
            settings=replace(Settings(), microphone_consent=True),
            remote=self.remote,
            audio=self.audio,
            schedule=self.scheduler.schedule,
            dispatch=lambda f: f(),
            clock=lambda: self.scheduler.now,
        )
        self.controller.prepare_model()
        self.controller.connect()
        self.remote.grant()
        self.save = CustomShortcut(
            "save", "save file", "Ctrl+S", "Save current document"
        )

    def review(self, text="hello", mode=Mode.DICTATION):
        self.controller.start_recording(mode)
        self.controller.finish_recording()
        self.audio.callbacks["on_result"](text)
        return self.controller.snapshot.pending

    def custom_api(self):
        self.assertTrue(
            hasattr(self.controller, "replace_custom_shortcuts"),
            "Custom controller API missing",
        )
        self.controller.replace_custom_shortcuts((self.save,))

    def test_custom_chord_reviews_and_executes_with_two_distinct_confirmations(self):
        self.custom_api()
        action = self.review("save file", Mode.COMMANDS)
        self.assertEqual(action.key_chord, "Ctrl+S")
        self.controller.shortcut_event("confirm", False)
        self.controller.shortcut_event("confirm", False)
        self.scheduler.advance(5)
        self.assertFalse(self.remote.actions)
        self.controller.confirm_second(action.id)
        self.scheduler.advance(3)
        self.assertEqual(self.remote.actions[0], action)

    def test_catalogue_change_cancels_capture_draft_and_late_result(self):
        self.custom_api()
        self.controller.start_recording(Mode.COMMANDS)
        callbacks = dict(self.audio.callbacks)
        callbacks["on_draft"]("save file")
        self.controller.replace_custom_shortcuts(
            (replace(self.save, key_chord="Alt+S"),)
        )
        callbacks["on_result"]("save file")
        self.assertEqual(self.controller.snapshot.state, State.IDLE)
        self.assertEqual(self.controller.snapshot.draft_text, "")
        self.assertIsNone(self.controller.snapshot.pending)
        self.assertEqual(self.controller.snapshot.commands["save"].key_chord, "Alt+S")

    def test_manager_add_update_delete_and_reset_cancel_armed_input(self):
        self.custom_api()
        action = self.review("save file", Mode.COMMANDS)
        self.controller.confirm(action.id)
        self.controller.confirm_second(action.id)
        self.controller.delete_custom_shortcut("save")
        self.controller.shortcut_event("confirm", False)
        self.scheduler.advance(10)
        self.assertFalse(self.remote.actions)
        self.controller.add_custom_shortcut(self.save)
        self.controller.update_custom_shortcut(replace(self.save, enabled=False))
        self.assertNotIn("save", self.controller.snapshot.commands)
        self.assertFalse(self.controller.snapshot.custom_shortcuts[0].enabled)
        with self.assertRaises(DomainError):
            self.controller.add_custom_shortcut(self.save)

    def test_begin_edit_disarms_global_confirm_and_countdown_while_buffer_can_be_empty(
        self,
    ):
        action = self.review()
        self.controller.confirm(action.id)
        self.assertTrue(
            hasattr(self.controller, "begin_edit"), "Staged controller editing missing"
        )
        token = self.controller.begin_edit(action.id)
        self.controller.shortcut_event("confirm", False)
        self.assertEqual(self.controller.snapshot.state, State.EDITING)
        self.assertIsNone(self.controller.snapshot.pending)
        self.assertEqual(self.controller.snapshot.countdown_seconds, 0)
        self.assertFalse(self.controller.finish_edit(token, ""))
        self.scheduler.advance(10)
        self.assertFalse(self.remote.actions)
        self.assertTrue(self.controller.finish_edit(token, "replacement"))
        newer = self.controller.snapshot.pending
        self.assertFalse(self.controller.finish_edit(token, "stale"))
        self.assertEqual(self.controller.snapshot.pending, newer)
        self.assertNotEqual(newer.id, action.id)

    def test_edit_second_confirmation_resets_all_approval_and_stale_begin_keeps_timer(
        self,
    ):
        action = self.review("press enter", Mode.COMMANDS)
        self.controller.confirm(action.id)
        self.assertTrue(
            hasattr(self.controller, "begin_edit"), "Staged controller editing missing"
        )
        token = self.controller.begin_edit(action.id)
        self.controller.finish_edit(token, "press enter")
        new = self.controller.snapshot.pending
        self.controller.confirm(new.id)
        self.controller.confirm_second(new.id)
        self.assertIsNone(self.controller.begin_edit(action.id))
        self.scheduler.advance(3)
        self.assertEqual(self.remote.actions[0], new)

    def test_practice_preview_records_only_simulated_reviewed_plan_and_never_touches_audio(
        self,
    ):
        self.custom_api()
        practice = Controller(
            settings=Settings(),
            remote=PracticeInput(),
            audio=self.audio,
            schedule=self.scheduler.schedule,
            dispatch=lambda f: f(),
            clock=lambda: self.scheduler.now,
            practice=True,
            custom_shortcuts=(self.save,),
        )
        practice.review_text("save file", Mode.COMMANDS)
        action = practice.snapshot.pending
        practice.confirm(action.id)
        practice.confirm_second(action.id)
        self.scheduler.advance(3)
        self.assertEqual(practice.snapshot.practice_last_action, action)
        self.assertIn("no desktop input", practice.snapshot.status)
        self.assertFalse(self.audio.callbacks)
        self.assertFalse(self.remote.actions)

    def test_persistent_controller_loads_configuration_and_reset_clears_it(self):
        import tempfile
        from pathlib import Path

        from wayland_voice_control.storage import SettingsStore

        with tempfile.TemporaryDirectory() as directory:
            store = SettingsStore(Path(directory) / "private" / "settings.db")
            store.add_custom_shortcut(self.save)
            controller = Controller(
                settings=store.load(),
                store=store,
                remote=PracticeInput(),
                audio=self.audio,
                schedule=self.scheduler.schedule,
                dispatch=lambda f: f(),
                practice=True,
            )
            self.assertEqual(controller.snapshot.custom_shortcuts, (self.save,))
            controller.delete_custom_shortcut("save")
            self.assertEqual(store.load_custom_shortcuts(), ())
            controller.add_custom_shortcut(self.save)
            controller.review_text("save file", Mode.COMMANDS)
            controller.reset_settings()
            self.assertIsNone(controller.snapshot.pending)
            self.assertEqual(controller.snapshot.custom_shortcuts, ())
            self.assertEqual(store.load_configuration(), (Settings(), ()))

    def test_catalogue_change_cancels_executing_action_without_mutating_plan_or_accepting_late_completion(
        self,
    ):
        self.custom_api()
        old = self.review("save file", Mode.COMMANDS)
        self.controller.confirm(old.id)
        self.controller.confirm_second(old.id)
        self.scheduler.advance(3)
        self.controller.update_custom_shortcut(replace(self.save, key_chord="Alt+F4"))
        self.assertEqual(self.remote.actions[0].key_chord, "Ctrl+S")
        newer = self.review("save file", Mode.COMMANDS)
        self.remote.completions[0](RuntimeError("old input cancelled"))
        self.assertEqual(self.controller.snapshot.pending, newer)
        self.assertEqual(newer.key_chord, "Alt+F4")

    def test_invalid_manager_items_raise_validation_errors_without_cancelling_review(
        self,
    ):
        self.custom_api()
        action = self.review()
        for value in (None, 1, {}, "save"):
            for method in (
                self.controller.add_custom_shortcut,
                self.controller.update_custom_shortcut,
            ):
                with self.subTest(value=value, method=method.__name__):
                    try:
                        method(value)
                    except DomainError:
                        pass
                    except (AttributeError, TypeError) as error:
                        self.fail(
                            f"Malformed manager data needs DomainError, got {type(error).__name__}"
                        )
                    else:
                        self.fail("Malformed manager item was accepted")
                    self.assertEqual(self.controller.snapshot.pending, action)

    def test_two_controllers_preserve_other_item_changes_with_stale_catalogues(self):
        import tempfile
        from pathlib import Path

        from wayland_voice_control.storage import SettingsStore

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "private" / "settings.db"
            store_a, store_b = SettingsStore(path), SettingsStore(path)

            def controller(store):
                return Controller(
                    settings=store.load(),
                    store=store,
                    remote=PracticeInput(),
                    audio=self.audio,
                    schedule=self.scheduler.schedule,
                    dispatch=lambda f: f(),
                    practice=True,
                )

            first, second = controller(store_a), controller(store_b)
            opened = CustomShortcut("open", "open file", "Ctrl+O")
            first.add_custom_shortcut(self.save)
            second.add_custom_shortcut(opened)
            self.assertEqual(store_a.load_custom_shortcuts(), (self.save, opened))
            disabled = replace(self.save, enabled=False)
            first.update_custom_shortcut(disabled)
            self.assertEqual(store_a.load_custom_shortcuts(), (disabled, opened))
            # Second still holds the old enabled save entry: deleting open must
            # neither resurrect that flag nor remove an unrelated new entry.
            third = CustomShortcut("print", "print file", "Ctrl+P")
            first.add_custom_shortcut(third)
            second.delete_custom_shortcut("open")
            self.assertEqual(second.snapshot.custom_shortcuts, (disabled, third))
            self.assertEqual(store_a.load_custom_shortcuts(), (disabled, third))
            # Also allow operations on IDs absent from this controller's cache.
            second.add_custom_shortcut(opened)
            first.update_custom_shortcut(replace(opened, key_chord="Alt+O"))
            first.delete_custom_shortcut("open")
            second.delete_custom_shortcut("print")
            second.add_custom_shortcut(third)
            self.assertEqual(store_a.load_custom_shortcuts(), (disabled, third))
            unseen = CustomShortcut("unseen", "new phrase", "Ctrl+N")
            store_b.add_custom_shortcut(unseen)
            first.update_custom_shortcut(replace(unseen, enabled=False))
            unseen_delete = CustomShortcut("unseen-delete", "delete phrase", "Ctrl+D")
            store_b.add_custom_shortcut(unseen_delete)
            first.delete_custom_shortcut(unseen_delete.id)
            self.assertEqual(
                store_a.load_custom_shortcuts(),
                (disabled, third, replace(unseen, enabled=False)),
            )

    def test_item_validation_precedes_cancel_and_storage_failure_keeps_old_catalogue_disarmed(
        self,
    ):
        import tempfile
        from pathlib import Path

        from wayland_voice_control.storage import SettingsError, SettingsStore

        with tempfile.TemporaryDirectory() as directory:
            controller = self.controller

            class Store(SettingsStore):
                fail = False

                def add_custom_shortcut(self, item):
                    self_test.assertIsNone(controller.snapshot.pending)
                    self_test.assertEqual(controller.snapshot.state, State.IDLE)
                    if self.fail:
                        raise SettingsError("test write failure")
                    return super().add_custom_shortcut(item)

            self_test = self
            store = Store(Path(directory) / "private" / "settings.db")
            controller.store = store
            controller.add_custom_shortcut(self.save)
            action = self.review()
            with self.assertRaises(DomainError):
                controller.add_custom_shortcut(
                    replace(self.save, id="duplicate-phrase")
                )
            self.assertEqual(controller.snapshot.pending, action)
            controller.confirm(action.id)
            store.fail = True
            with self.assertRaises(SettingsError):
                controller.add_custom_shortcut(
                    CustomShortcut("open", "open file", "Ctrl+O")
                )
            self.assertIsNone(controller.snapshot.pending)
            self.assertEqual(controller.snapshot.custom_shortcuts, (self.save,))
            self.assertEqual(store.load_custom_shortcuts(), (self.save,))
            self.scheduler.advance(10)
            self.assertFalse(self.remote.actions)

    def test_reset_revokes_and_disarms_before_store_write_even_when_reset_fails(self):
        from wayland_voice_control.storage import SettingsError

        self.custom_api()
        action = self.review()
        self.controller.confirm(action.id)
        controller = self.controller
        old_settings = controller.settings
        self_test = self

        class Store:
            def reset(self):
                self_test.assertIsNone(controller.snapshot.pending)
                self_test.assertFalse(controller.snapshot.permission_granted)
                self_test.assertGreater(self_test.remote.closed, 0)
                self_test.assertEqual(controller.snapshot.countdown_seconds, 0)
                raise SettingsError("test reset failure")

        controller.store = Store()
        with self.assertRaises(SettingsError):
            controller.reset_settings()
        self.assertEqual(controller.settings, old_settings)
        self.assertEqual(controller.snapshot.custom_shortcuts, (self.save,))
        self.assertIsNone(controller.snapshot.pending)
        self.scheduler.advance(10)
        self.assertFalse(self.remote.actions)

    def test_update_settings_and_custom_mutations_reject_worker_before_store_changes(
        self,
    ):
        class Store:
            calls = 0

            def update(self, changes):
                self.calls += 1
                return Settings()

        store = Store()
        self.controller.store = store
        errors = []

        def worker():
            try:
                self.controller.update_settings({"theme": "dark"})
            except RuntimeError as error:
                errors.append(error)

        thread = threading.Thread(target=worker)
        thread.start()
        thread.join()
        self.assertEqual(len(errors), 1)
        self.assertEqual(store.calls, 0)
