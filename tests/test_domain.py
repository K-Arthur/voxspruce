import dataclasses
import itertools
import unittest

from tests import require_module


class DictationTests(unittest.TestCase):
    def setUp(self):
        self.domain = require_module(self, "wayland_voice_control.domain")

    def test_dictation_preserves_literal_text_and_unicode(self):
        for text in ("press enter", "  Keep these spaces.  ", "Bonjour — café 日本語!"):
            self.assertEqual(self.domain.validate_dictation(text), text)

    def test_empty_and_overlong_dictation_is_rejected(self):
        for text in ("", "  ", "a" * 4001):
            with (
                self.subTest(length=len(text)),
                self.assertRaises(self.domain.DomainError),
            ):
                self.domain.validate_dictation(text)
        self.assertEqual(len(self.domain.validate_dictation("a" * 4000)), 4000)

    def test_control_format_and_surrogate_characters_are_rejected(self):
        characters = [chr(value) for value in range(32)] + [
            chr(value) for value in range(127, 160)
        ]
        characters += [
            "\u202e",
            "\u2066",
            "\u200b",
            "\ufeff",
            "\ud800",
            "\u2028",
            "\u2029",
        ]
        for character in characters:
            with (
                self.subTest(code=ord(character)),
                self.assertRaises(self.domain.DomainError),
            ):
                self.domain.validate_dictation("hello" + character + "world")

    def test_non_strings_are_rejected(self):
        for value in (None, 42, True, b"text"):
            with self.subTest(value=value), self.assertRaises(self.domain.DomainError):
                self.domain.validate_dictation(value)


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.domain = require_module(self, "wayland_voice_control.domain")
        self.assertTrue(
            hasattr(self.domain, "Workflow"),
            "Approval workflow has not been implemented",
        )
        self.now = 100.0
        ids = itertools.count()
        self.workflow = self.domain.Workflow(
            clock=lambda: self.now, id_factory=lambda: f"id-{next(ids)}"
        )

    def enable(self):
        self.workflow.set_permission(True)
        self.workflow.set_microphone_consent(True)

    def review(self, text="copy", mode=None):
        self.enable()
        recording = self.workflow.begin_recording(mode or self.domain.Mode.COMMANDS)
        self.assertEqual(self.workflow.state, self.domain.State.RECORDING)
        self.workflow.finish_recording(recording)
        self.assertEqual(self.workflow.state, self.domain.State.PROCESSING)
        return self.workflow.receive_transcript(recording, text)

    def test_permission_and_consent_are_both_required(self):
        self.assertEqual(self.workflow.state, self.domain.State.IDLE)
        for permission, consent in ((False, False), (False, True), (True, False)):
            self.workflow.set_permission(permission)
            self.workflow.set_microphone_consent(consent)
            with (
                self.subTest(permission=permission, consent=consent),
                self.assertRaisesRegex(self.domain.DomainError, "permission|consent"),
            ):
                self.workflow.begin_recording(self.domain.Mode.DICTATION)
            self.assertEqual(self.workflow.state, self.domain.State.IDLE)

    def test_transcript_only_creates_immutable_review_action(self):
        action = self.review()
        self.assertEqual(self.workflow.state, self.domain.State.REVIEWING)
        self.assertEqual(action.kind, self.domain.ActionKind.COMMAND)
        self.assertEqual(action.payload, "copy")
        self.assertEqual(action.created_at, 100)
        self.assertEqual(action.expires_at, 130)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            action.payload = "paste"
        with self.assertRaises(self.domain.DomainError):
            self.workflow.take_action(action.id)

    def test_dictation_command_words_are_literal_text(self):
        action = self.review("press enter", self.domain.Mode.DICTATION)
        self.assertEqual(action.kind, self.domain.ActionKind.TEXT)
        self.assertEqual(action.payload, "press enter")
        self.assertEqual(action.risk, self.domain.Risk.NORMAL)

    def test_single_confirmation_arms_normal_action_and_take_consumes_once(self):
        action = self.review()
        self.assertEqual(self.workflow.confirm(action.id), self.domain.State.ARMED)
        self.assertEqual(self.workflow.take_action(action.id), action)
        self.assertEqual(self.workflow.state, self.domain.State.EXECUTING)
        self.assertIsNone(self.workflow.pending)
        with self.assertRaises(self.domain.DomainError):
            self.workflow.take_action(action.id)
        self.workflow.complete_execution()
        self.assertEqual(self.workflow.state, self.domain.State.IDLE)
        with self.assertRaises(self.domain.DomainError):
            self.workflow.take_action(action.id)

    def test_high_risk_requires_distinct_second_confirmation_method(self):
        for phrase in ("press enter", "close window", "delete selection"):
            with self.subTest(phrase=phrase):
                action = self.review(phrase)
                with self.assertRaises(self.domain.DomainError):
                    self.workflow.confirm_second(action.id)
                self.assertEqual(
                    self.workflow.confirm(action.id),
                    self.domain.State.AWAITING_SECOND_CONFIRMATION,
                )
                with self.assertRaises(self.domain.DomainError):
                    self.workflow.confirm(action.id)
                with self.assertRaises(self.domain.DomainError):
                    self.workflow.take_action(action.id)
                self.assertEqual(
                    self.workflow.confirm_second(action.id), self.domain.State.ARMED
                )
                self.assertEqual(self.workflow.take_action(action.id), action)
                self.workflow.complete_execution()

    def test_wrong_action_ids_cannot_confirm_edit_or_execute(self):
        action = self.review("close window")
        for operation in (
            lambda: self.workflow.confirm("stale"),
            lambda: self.workflow.edit_pending("stale", "copy"),
        ):
            with self.assertRaisesRegex(self.domain.DomainError, "Stale"):
                operation()
        self.workflow.confirm(action.id)
        with self.assertRaisesRegex(self.domain.DomainError, "Stale"):
            self.workflow.confirm_second("stale")
        self.workflow.confirm_second(action.id)
        with self.assertRaisesRegex(self.domain.DomainError, "Stale"):
            self.workflow.take_action("stale")
        self.assertEqual(self.workflow.pending, action)

    def test_edit_creates_new_identity_and_removes_all_approvals(self):
        original = self.review("press enter")
        self.workflow.confirm(original.id)
        self.workflow.confirm_second(original.id)
        self.now = 110
        changed = self.workflow.edit_pending(original.id, "close window")
        self.assertNotEqual(original.id, changed.id)
        self.assertEqual(changed.expires_at, 140)
        self.assertEqual(self.workflow.state, self.domain.State.REVIEWING)
        with self.assertRaises(self.domain.DomainError):
            self.workflow.confirm(original.id)
        with self.assertRaises(self.domain.DomainError):
            self.workflow.take_action(changed.id)
        self.workflow.confirm(changed.id)
        self.assertEqual(
            self.workflow.state, self.domain.State.AWAITING_SECOND_CONFIRMATION
        )

    def test_invalid_edit_revokes_old_approvals(self):
        action = self.review()
        self.workflow.confirm(action.id)
        with self.assertRaises(self.domain.DomainError):
            self.workflow.edit_pending(action.id, "copy and paste")
        self.assertIsNone(self.workflow.pending)
        self.assertEqual(self.workflow.state, self.domain.State.ERROR)
        with self.assertRaises(self.domain.DomainError):
            self.workflow.take_action(action.id)

    def test_expiry_is_enforced_at_each_approval_and_execution_boundary(self):
        for phase in ("first", "second", "execution", "edit"):
            with self.subTest(phase=phase):
                self.workflow.reset()
                action = self.review("press enter")
                if phase in ("second", "execution"):
                    self.workflow.confirm(action.id)
                if phase == "execution":
                    self.workflow.confirm_second(action.id)
                self.now = action.expires_at
                operation = {
                    "first": lambda action=action: self.workflow.confirm(action.id),
                    "second": lambda action=action: self.workflow.confirm_second(
                        action.id
                    ),
                    "execution": lambda action=action: self.workflow.take_action(
                        action.id
                    ),
                    "edit": lambda action=action: self.workflow.edit_pending(
                        action.id, "copy"
                    ),
                }[phase]
                with self.assertRaisesRegex(self.domain.DomainError, "expired"):
                    operation()
                self.assertIsNone(self.workflow.pending)

    def test_stop_disconnect_and_revocation_cancel_recording_and_armed_actions(self):
        for cancel in (
            self.workflow.stop,
            self.workflow.disconnect,
            self.workflow.revoke_permission,
            lambda: self.workflow.set_microphone_consent(False),
            lambda: self.workflow.set_permission(False),
        ):
            for phase in ("recording", "armed"):
                with self.subTest(cancel=cancel, phase=phase):
                    self.workflow.reset()
                    self.enable()
                    if phase == "recording":
                        recording = self.workflow.begin_recording(
                            self.domain.Mode.DICTATION
                        )
                        cancel()
                        with self.assertRaises(self.domain.DomainError):
                            self.workflow.finish_recording(recording)
                    else:
                        action = self.review()
                        self.workflow.confirm(action.id)
                        cancel()
                        with self.assertRaises(self.domain.DomainError):
                            self.workflow.take_action(action.id)
                    self.assertEqual(self.workflow.state, self.domain.State.IDLE)
                    self.assertIsNone(self.workflow.pending)

    def test_stale_recognition_cannot_attach_to_a_new_recording(self):
        self.enable()
        old = self.workflow.begin_recording(self.domain.Mode.DICTATION)
        self.workflow.stop()
        current = self.workflow.begin_recording(self.domain.Mode.COMMANDS)
        self.workflow.finish_recording(current)
        with self.assertRaisesRegex(self.domain.DomainError, "Stale"):
            self.workflow.receive_transcript(old, "delete selection")
        self.assertEqual(self.workflow.state, self.domain.State.PROCESSING)
        self.assertEqual(
            self.workflow.receive_transcript(current, "copy").payload, "copy"
        )

    def test_invalid_transitions_are_rejected(self):
        for operation in (
            lambda: self.workflow.finish_recording("missing"),
            lambda: self.workflow.receive_transcript("missing", "copy"),
            lambda: self.workflow.confirm("missing"),
            self.workflow.complete_execution,
        ):
            with self.assertRaises(self.domain.DomainError):
                operation()
        self.enable()
        with self.assertRaises(self.domain.DomainError):
            self.workflow.begin_recording("commands")
        self.workflow.begin_recording(self.domain.Mode.COMMANDS)
        with self.assertRaises(self.domain.DomainError):
            self.workflow.begin_recording(self.domain.Mode.DICTATION)

    def test_error_clears_transient_data_and_reset_allows_recovery(self):
        action = self.review()
        self.workflow.fail("Microphone is unavailable.")
        self.assertEqual(self.workflow.state, self.domain.State.ERROR)
        self.assertEqual(self.workflow.error, "Microphone is unavailable.")
        self.assertIsNone(self.workflow.pending)
        with self.assertRaises(self.domain.DomainError):
            self.workflow.confirm(action.id)
        self.workflow.reset()
        self.assertIsNone(self.workflow.error)
        self.assertEqual(self.review().payload, "copy")

    def test_invalid_transcript_enters_recoverable_error_without_pending_action(self):
        self.enable()
        recording = self.workflow.begin_recording(self.domain.Mode.COMMANDS)
        self.workflow.finish_recording(recording)
        with self.assertRaises(self.domain.DomainError):
            self.workflow.receive_transcript(recording, "copy then paste")
        self.assertEqual(self.workflow.state, self.domain.State.ERROR)
        self.assertIsNone(self.workflow.pending)

    def test_instances_do_not_share_consent_permission_or_pending_data(self):
        self.review()
        other = self.domain.Workflow()
        self.assertEqual(other.state, self.domain.State.IDLE)
        self.assertIsNone(other.pending)
        with self.assertRaises(self.domain.DomainError):
            other.begin_recording(self.domain.Mode.DICTATION)

    def test_ttl_is_configurable_and_invalid_numbers_are_rejected(self):
        self.workflow = self.domain.Workflow(
            confirmation_ttl_seconds=10, clock=lambda: self.now
        )
        action = self.review()
        self.assertEqual(action.expires_at, 110)
        for value in (True, 0, 9, 121, 10**1000, float("inf"), float("nan"), "30"):
            with self.subTest(value=value), self.assertRaises(self.domain.DomainError):
                self.domain.Workflow(confirmation_ttl_seconds=value)

    def test_gate_values_must_be_actual_booleans(self):
        for value in (1, 0, "yes", None):
            for operation in (
                self.workflow.set_permission,
                self.workflow.set_microphone_consent,
            ):
                with (
                    self.subTest(value=value),
                    self.assertRaises(self.domain.DomainError),
                ):
                    operation(value)

    def test_injected_duplicate_identity_is_rejected_without_reusing_action(self):
        self.workflow = self.domain.Workflow(id_factory=lambda: "duplicate")
        self.enable()
        recording = self.workflow.begin_recording(self.domain.Mode.DICTATION)
        self.workflow.finish_recording(recording)
        with self.assertRaisesRegex(self.domain.DomainError, "identity"):
            self.workflow.receive_transcript(recording, "hello")
        self.assertIsNone(self.workflow.pending)


if __name__ == "__main__":
    unittest.main()
