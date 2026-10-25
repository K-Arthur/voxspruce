import unittest

from wayland_voice_control.commands import CustomShortcut
from wayland_voice_control.domain import DomainError, Mode, Risk, State, Workflow


class StagedEditingTests(unittest.TestCase):
    def setUp(self):
        self.now = 0
        self.workflow = Workflow(clock=lambda: self.now)
        self.workflow.set_permission(True)
        self.workflow.set_microphone_consent(True)

    def review(self, text="hello", mode=Mode.DICTATION):
        recording = self.workflow.begin_recording(mode)
        self.workflow.finish_recording(recording)
        return self.workflow.receive_transcript(recording, text)

    def begin(self, action):
        self.assertTrue(
            hasattr(self.workflow, "begin_edit"), "Staged editing is missing"
        )
        return self.workflow.begin_edit(action.id)

    def test_empty_intermediate_edit_stays_correctable_with_no_approved_action(self):
        old = self.review()
        self.workflow.confirm(old.id)
        token = self.begin(old)
        self.assertEqual(self.workflow.state.value, "editing")
        self.assertIsNone(self.workflow.pending)
        with self.assertRaises(DomainError):
            self.workflow.confirm(old.id)
        for text in ("", "bad\ntext"):
            with self.assertRaises(DomainError):
                self.workflow.finish_edit(token, text)
            self.assertEqual(self.workflow.state.value, "editing")
            self.assertIsNone(self.workflow.pending)
        self.now = 5
        new = self.workflow.finish_edit(token, "replacement")
        self.assertNotEqual(new.id, old.id)
        self.assertEqual((new.created_at, new.expires_at), (5, 35))
        self.assertEqual(self.workflow.state, State.REVIEWING)
        with self.assertRaises(DomainError):
            self.workflow.take_action(new.id)

    def test_stale_edit_cannot_discard_newer_work_and_cancel_discards_edit(self):
        old = self.review()
        token = self.begin(old)
        self.workflow.cancel()
        new = self.review("newer")
        for call in (
            lambda: self.workflow.begin_edit(old.id),
            lambda: self.workflow.finish_edit(token, "old"),
        ):
            with self.assertRaises(DomainError):
                call()
            self.assertIs(self.workflow.pending, new)
        self.workflow.begin_edit(new.id)
        self.workflow.cancel()
        self.assertEqual(self.workflow.state, State.IDLE)

    def test_start_edit_checks_original_expiry(self):
        old = self.review()
        self.assertTrue(
            hasattr(self.workflow, "begin_edit"), "Staged editing is missing"
        )
        self.now = old.expires_at
        with self.assertRaises(DomainError):
            self.workflow.begin_edit(old.id)
        self.assertIsNone(self.workflow.pending)

    def test_custom_action_binds_chord_phrase_description_at_review_and_requires_second_confirm(
        self,
    ):
        self.assertTrue(
            hasattr(self.workflow, "set_custom_shortcuts"),
            "Workflow catalogue API missing",
        )
        self.workflow.set_custom_shortcuts(
            (CustomShortcut("save", "save file", "Ctrl+S", "Save"),)
        )
        action = self.review("SAVE FILE", Mode.COMMANDS)
        self.assertEqual(
            (action.key_chord, action.phrase, action.description, action.risk),
            ("Ctrl+S", "save file", "Save", Risk.HIGH),
        )
        self.assertEqual(
            self.workflow.confirm(action.id), State.AWAITING_SECOND_CONFIRMATION
        )
        with self.assertRaises(DomainError):
            self.workflow.take_action(action.id)
        self.workflow.set_custom_shortcuts(
            (CustomShortcut("save", "save file", "Alt+F4"),)
        )
        self.assertIsNone(self.workflow.pending)
        self.assertEqual(action.key_chord, "Ctrl+S")
        with self.assertRaises(DomainError):
            self.workflow.confirm_second(action.id)
