import unittest
from dataclasses import replace

from wayland_voice_control import ui_model
from wayland_voice_control.controller import Controller, PracticeInput
from wayland_voice_control.domain import Mode
from wayland_voice_control.storage import Settings


class PresentationTests(unittest.TestCase):
    def setUp(self):
        self.controller = Controller(
            settings=Settings(),
            remote=PracticeInput(),
            audio=None,
            dispatch=lambda f: f(),
            schedule=lambda seconds, f: lambda: None,
            practice=True,
        )

    def test_capture_needs_model_consent_grant_and_live_mode(self):
        snapshot = self.controller.snapshot
        self.assertFalse(ui_model.can_capture(snapshot))
        ready = replace(
            snapshot,
            practice=False,
            microphone_consent=True,
            permission_granted=True,
            model_readiness="ready",
        )
        self.assertTrue(ui_model.can_capture(ready))
        for field, value in [
            ("microphone_consent", False),
            ("permission_granted", False),
            ("model_readiness", "loading"),
        ]:
            self.assertFalse(ui_model.can_capture(replace(ready, **{field: value})))

    def test_capture_control_stays_disabled_until_pending_work_is_cancelled(self):
        from wayland_voice_control.domain import State

        ready = replace(
            self.controller.snapshot,
            practice=False,
            microphone_consent=True,
            permission_granted=True,
            model_readiness="ready",
        )
        for state in State:
            self.assertEqual(
                ui_model.can_capture(replace(ready, state=state)), state is State.IDLE
            )

    def test_review_displays_exact_immutable_custom_details(self):
        from wayland_voice_control.commands import CustomShortcut

        self.controller.add_custom_shortcut(
            CustomShortcut(
                "save", "save document", "Ctrl+S", "Save the current document"
            )
        )
        self.controller.review_text("save document", Mode.COMMANDS)
        text = ui_model.action_details(self.controller.snapshot.pending)
        for value in [
            "save document",
            "Ctrl+S",
            "Save the current document",
            "High risk",
            "Custom",
            "two",
        ]:
            self.assertIn(value, text)

    def test_practice_factory_does_not_construct_live_adapters(self):
        controller = ui_model.create_controller(practice=True)
        self.assertTrue(controller.practice)
        self.assertIsInstance(controller.remote, PracticeInput)
        self.assertIsNone(controller.audio)
        self.assertIsNone(controller.shortcuts)


if __name__ == "__main__":
    unittest.main()
