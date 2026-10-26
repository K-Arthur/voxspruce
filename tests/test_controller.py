import unittest
from dataclasses import replace

from wayland_voice_control.controller import Controller, PracticeInput
from wayland_voice_control.domain import Mode, State
from wayland_voice_control.storage import Settings


class Audio:
    def __init__(self):
        self.callbacks = {}
        self.cancelled = 0
        self.preparations = []

    def prepare(self, path, **kwargs):
        self.preparations.append(kwargs)
        kwargs["on_state"]("ready")
        return True

    def start(self, path, **kwargs):
        self.callbacks = kwargs
        kwargs["on_activity"]("loading")
        return True

    def stop(self):
        pass

    def cancel(self):
        self.cancelled += 1


class Remote:
    def __init__(self):
        self.granted = False
        self.actions = []
        self.completions = []
        self.closed = 0
        self.cancelled = 0

    def connect(self, callback, parent_window=""):
        self.connected = callback

    def grant(self):
        self.granted = True
        self.connected(True, None)

    def execute(self, action, callback):
        self.actions.append(action)
        self.completions.append(callback)

    def cancel_input(self):
        self.cancelled += 1

    def close(self):
        self.closed += 1
        self.granted = False


class Scheduler:
    def __init__(self):
        self.now = 0
        self.jobs = []

    def schedule(self, seconds, callback):
        job = [self.now + seconds, callback, False]
        self.jobs.append(job)
        return lambda: job.__setitem__(2, True)

    def advance(self, seconds):
        target = self.now + seconds
        while True:
            ready = [job for job in self.jobs if not job[2] and job[0] <= target]
            if not ready:
                break
            job = min(ready, key=lambda j: j[0])
            self.now = job[0]
            job[2] = True
            job[1]()
        self.now = target


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.remote, self.audio, self.scheduler = Remote(), Audio(), Scheduler()
        self.settings = replace(
            Settings(), microphone_consent=True, model_path="/model"
        )
        self.controller = Controller(
            settings=self.settings,
            remote=self.remote,
            audio=self.audio,
            schedule=self.scheduler.schedule,
            dispatch=lambda f: f(),
            clock=lambda: self.scheduler.now,
        )
        self.controller.prepare_model()
        self.controller.connect()
        self.remote.grant()

    def review(self, text="hello", mode=Mode.DICTATION):
        self.controller.start_recording(mode)
        self.audio.callbacks["on_activity"]("recording")
        self.controller.finish_recording()
        self.audio.callbacks["on_result"](text)
        return self.controller.snapshot.pending.id

    def test_local_and_global_hold_require_an_explicitly_prepared_model(self):
        self.controller.apply_settings(self.settings)
        self.assertEqual(self.controller.snapshot.model_readiness, "idle")

        self.assertFalse(self.controller.start_recording())
        self.controller.shortcut_event("hold_to_talk", True)

        self.assertEqual(self.controller.snapshot.state, State.IDLE)
        self.assertEqual(self.controller.snapshot.model_readiness, "idle")
        self.assertNotIn("on_result", self.audio.callbacks)
        self.assertIn("prepare", self.controller.snapshot.status.lower())

    def test_loading_or_failed_model_blocks_capture_until_preparation_is_ready(self):
        preparation = []
        self.audio.prepare = lambda path, **kwargs: preparation.append(kwargs) or True
        self.assertTrue(self.controller.prepare_model())
        self.assertEqual(self.controller.snapshot.model_readiness, "loading")
        self.assertFalse(self.controller.start_recording())

        preparation[-1]["on_state"]("error")
        self.assertFalse(self.controller.start_recording())
        self.assertNotIn("on_result", self.audio.callbacks)

        preparation[-1]["on_state"]("ready")
        self.assertTrue(self.controller.start_recording())

    def test_full_flow_review_confirmation_countdown_and_completion(self):
        action_id = self.review()
        self.assertEqual(self.controller.snapshot.state, State.REVIEWING)
        self.assertFalse(self.remote.actions)
        self.controller.confirm(action_id)
        self.assertEqual(self.controller.snapshot.countdown_seconds, 3)
        self.scheduler.advance(2)
        self.assertFalse(self.remote.actions)
        self.scheduler.advance(1)
        self.assertEqual(self.controller.snapshot.state, State.EXECUTING)
        self.assertEqual(self.remote.actions[0].payload, "hello")
        self.remote.completions[0](None)
        self.assertEqual(self.controller.snapshot.state, State.IDLE)

    def test_risky_action_requires_distinct_second_confirmation(self):
        action_id = self.review("press enter", Mode.COMMANDS)
        self.controller.confirm(action_id, source="global")
        self.controller.confirm(action_id, source="global")
        self.scheduler.advance(10)
        self.assertEqual(
            self.controller.snapshot.state, State.AWAITING_SECOND_CONFIRMATION
        )
        self.assertFalse(self.remote.actions)
        self.controller.confirm_second(action_id)
        self.scheduler.advance(3)
        self.assertEqual(len(self.remote.actions), 1)

    def test_edit_replaces_identity_and_cancels_scheduled_input(self):
        action_id = self.review()
        self.controller.confirm(action_id)
        self.controller.edit(action_id, "changed")
        self.scheduler.advance(10)
        self.assertFalse(self.remote.actions)
        self.assertNotEqual(self.controller.snapshot.pending.id, action_id)
        self.assertEqual(self.controller.snapshot.state, State.REVIEWING)

    def test_stop_cancels_everything_and_late_success_and_error_cannot_change_new_action(
        self,
    ):
        for error in (None, RuntimeError("late")):
            action_id = self.review()
            self.controller.confirm(action_id)
            self.scheduler.advance(3)
            complete = self.remote.completions[-1]
            self.controller.stop()
            self.assertFalse(self.controller.snapshot.permission_granted)
            self.assertIsNone(self.controller.snapshot.pending)
            self.controller.connect()
            self.remote.grant()
            self.review("new review")
            complete(error)
            self.assertEqual(self.controller.snapshot.state, State.REVIEWING)
            self.assertEqual(self.controller.snapshot.pending.payload, "new review")
            self.controller.cancel()

    def test_partial_input_failure_requires_reset_and_never_retries(self):
        action_id = self.review()
        self.controller.confirm(action_id)
        self.scheduler.advance(3)
        self.remote.completions[-1](RuntimeError("failed"))
        self.assertEqual(self.controller.snapshot.state, State.ERROR)
        self.assertIn("partially", self.controller.snapshot.error)
        self.assertFalse(self.controller.start_recording(Mode.DICTATION))
        self.scheduler.advance(10)
        self.assertEqual(len(self.remote.actions), 1)
        self.controller.reset_error()
        self.assertEqual(self.controller.snapshot.state, State.IDLE)

    def test_late_audio_after_cancel_cannot_revive_action(self):
        self.controller.start_recording(Mode.DICTATION)
        callbacks = self.audio.callbacks
        self.controller.cancel()
        callbacks["on_result"]("stale")
        callbacks["on_error"](RuntimeError("stale"))
        self.assertEqual(self.controller.snapshot.state, State.IDLE)
        self.assertIsNone(self.controller.snapshot.pending)

    def test_global_confirmation_has_short_release_settle(self):
        action_id = self.review()
        self.controller.confirm(action_id, source="global")
        self.assertFalse(self.remote.actions)
        self.scheduler.advance(0.1)
        self.assertFalse(self.remote.actions)
        self.scheduler.advance(0.1)
        self.assertEqual(len(self.remote.actions), 1)

    def test_recording_cap_completion_finishes_workflow_without_release(self):
        self.controller.start_recording(Mode.DICTATION)
        self.audio.callbacks["on_result"]("duration capped")
        self.assertEqual(self.controller.snapshot.state, State.REVIEWING)

    def test_update_settings_revokes_grants_and_pending(self):
        self.review()
        self.controller.apply_settings(replace(self.settings, microphone_consent=False))
        self.assertFalse(self.controller.snapshot.permission_granted)
        self.assertFalse(self.controller.snapshot.microphone_consent)
        self.assertIsNone(self.controller.snapshot.pending)
        self.assertFalse(self.controller.start_recording(Mode.DICTATION))

    def test_live_review_text_is_blocked_and_practice_uses_noop_only(self):
        with self.assertRaises(ValueError):
            self.controller.review_text("typed live")
        with self.assertRaises(ValueError):
            Controller(
                settings=self.settings,
                remote=self.remote,
                audio=self.audio,
                schedule=self.scheduler.schedule,
                dispatch=lambda f: f(),
                practice=True,
            )
        practice = Controller(
            settings=Settings(),
            remote=PracticeInput(),
            audio=self.audio,
            schedule=self.scheduler.schedule,
            dispatch=lambda f: f(),
            clock=lambda: self.scheduler.now,
            practice=True,
        )
        practice.review_text("practice only")
        practice.confirm(practice.snapshot.pending.id)
        self.scheduler.advance(3)
        self.assertEqual(practice.snapshot.state, State.IDLE)

    def test_observers_receive_immutable_snapshot(self):
        snapshots = []
        unsubscribe = self.controller.subscribe(snapshots.append)
        self.review()
        self.assertEqual(snapshots[-1].state, State.REVIEWING)
        unsubscribe()
        count = len(snapshots)
        self.controller.cancel()
        self.assertEqual(len(snapshots), count)

    def test_busy_audio_does_not_leave_recording_state(self):
        self.audio.start = lambda *args, **kwargs: False
        self.assertFalse(self.controller.start_recording(Mode.DICTATION))
        self.assertEqual(self.controller.snapshot.state, State.IDLE)

    def test_edit_invalidates_even_an_already_queued_timer_callback(self):
        action_id = self.review()
        self.controller.confirm(action_id)
        stale_tick = self.scheduler.jobs[-1][1]
        self.controller.edit(action_id, "changed")
        stale_tick()
        self.assertEqual(self.controller.snapshot.state, State.REVIEWING)
        self.assertFalse(self.remote.actions)

    def test_global_release_never_finishes_capture_started_by_another_source(self):
        self.assertTrue(self.controller.start_recording())
        self.audio.callbacks["on_activity"]("recording")
        self.controller.shortcut_event("hold_to_talk", True)
        self.controller.shortcut_event("hold_to_talk", False)
        self.assertEqual(self.controller.snapshot.state, State.RECORDING)
        self.controller.cancel()
        self.controller.shortcut_event("hold_to_talk", True)
        self.controller.shortcut_event("hold_to_talk", True)  # repeated key-down
        self.controller.shortcut_event("hold_to_talk", False)
        self.assertEqual(self.controller.snapshot.state, State.PROCESSING)

    def test_global_ownership_is_cleared_after_duration_cap_and_cancel(self):
        for finish in (
            lambda: self.audio.callbacks["on_result"]("capped"),
            self.controller.cancel,
        ):
            self.controller.shortcut_event("hold_to_talk", True)
            self.audio.callbacks["on_activity"]("recording")
            finish()
            self.controller.cancel()
            self.assertTrue(self.controller.start_recording())
            self.audio.callbacks["on_activity"]("recording")
            self.controller.shortcut_event("hold_to_talk", False)
            self.assertEqual(self.controller.snapshot.state, State.RECORDING)
            self.controller.cancel()

    def test_shortcut_events_use_selected_mode_and_never_second_confirm(self):
        self.controller.set_mode(Mode.COMMANDS)
        self.controller.shortcut_event("hold_to_talk", True)
        self.controller.shortcut_event("hold_to_talk", False)
        self.audio.callbacks["on_result"]("press enter")
        action_id = self.controller.snapshot.pending.id
        self.controller.shortcut_event("confirm", False)
        self.controller.shortcut_event("confirm", False)
        self.assertEqual(
            self.controller.snapshot.state, State.AWAITING_SECOND_CONFIRMATION
        )
        self.assertEqual(self.controller.snapshot.pending.id, action_id)
        self.controller.shortcut_event("cancel", False)
        self.assertEqual(self.controller.snapshot.state, State.IDLE)

    def test_practice_never_captures_audio_or_connects_global_shortcuts(self):
        calls = []
        self.audio.start = lambda *args, **kwargs: calls.append("microphone") or True

        class Shortcuts:
            def __init__(self):
                self.bindings = {}

            def connect(self, *args):
                calls.append("shortcut permission")

        practice = Controller(
            settings=self.settings,
            remote=PracticeInput(),
            audio=self.audio,
            schedule=self.scheduler.schedule,
            dispatch=lambda f: f(),
            shortcuts=Shortcuts(),
            practice=True,
        )
        self.assertFalse(practice.start_recording(Mode.DICTATION))
        practice.shortcut_event("hold_to_talk", True)
        practice.connect_shortcuts()
        self.assertEqual(calls, [])

    def test_local_capture_uses_explicitly_selected_mode(self):
        self.controller.set_mode(Mode.COMMANDS)
        self.controller.start_recording()
        self.audio.callbacks["on_result"]("press enter")
        self.assertEqual(self.controller.snapshot.pending.payload, "press_enter")

    def test_stale_edit_does_not_orphan_a_new_capture_completion(self):
        stale_id = self.review("old review")
        self.controller.cancel()
        self.assertTrue(self.controller.start_recording(Mode.DICTATION))
        self.assertFalse(self.controller.edit(stale_id, "late edit"))
        self.audio.callbacks["on_result"]("current recording")
        self.assertEqual(self.controller.snapshot.state, State.REVIEWING)
        self.assertEqual(self.controller.snapshot.pending.payload, "current recording")

    def test_edit_after_action_is_consumed_does_not_orphan_execution_completion(self):
        action_id = self.review()
        self.controller.confirm(action_id)
        self.scheduler.advance(3)
        self.assertFalse(self.controller.edit(action_id, "late edit"))
        self.remote.completions[-1](None)
        self.assertEqual(self.controller.snapshot.state, State.IDLE)

    def test_stale_edit_preserves_current_armed_countdown(self):
        stale_id = self.review("old review")
        self.controller.cancel()
        current_id = self.review("current review")
        self.controller.confirm(current_id)
        self.assertFalse(self.controller.edit(stale_id, "late edit"))
        self.scheduler.advance(3)
        self.assertEqual(self.controller.snapshot.state, State.EXECUTING)
        self.assertEqual(self.remote.actions[-1].payload, "current review")

    def test_invalid_content_edit_cancels_armed_dispatch_and_queued_tick(self):
        action_id = self.review()
        self.controller.confirm(action_id)
        stale_tick = self.scheduler.jobs[-1][1]
        self.assertFalse(self.controller.edit(action_id, ""))
        stale_tick()
        self.scheduler.advance(3)
        self.assertEqual(self.controller.snapshot.state, State.ERROR)
        self.assertEqual(self.controller.snapshot.countdown_seconds, 0)
        self.assertFalse(self.remote.actions)

    def test_drafts_are_transient_and_cannot_create_or_arm_actions(self):
        self.assertTrue(self.controller.start_recording())
        self.assertIn("on_draft", self.audio.callbacks)
        callbacks = self.audio.callbacks
        callbacks["on_draft"]("provisional speech")
        self.assertEqual(self.controller.snapshot.draft_text, "provisional speech")
        self.assertIsNone(self.controller.snapshot.pending)
        self.assertEqual(self.controller.snapshot.state, State.RECORDING)
        self.controller.finish_recording()
        self.assertEqual(self.controller.snapshot.draft_text, "")
        callbacks["on_draft"]("late provisional")
        self.assertEqual(self.controller.snapshot.draft_text, "")
        callbacks["on_result"]("final speech")
        callbacks["on_draft"]("even later")
        self.assertEqual(self.controller.snapshot.pending.payload, "final speech")
        self.assertEqual(self.controller.snapshot.draft_text, "")
        self.assertEqual(self.remote.actions, [])

    def test_model_preparation_needs_no_permission_and_stale_completions_are_ignored(
        self,
    ):
        self.assertTrue(hasattr(self.controller, "prepare_model"))
        preparations = []
        self.audio.prepare = lambda path, **kwargs: preparations.append(kwargs) or True
        self.controller.stop()
        self.controller.apply_settings(replace(self.settings, microphone_consent=False))
        self.assertTrue(self.controller.prepare_model())
        first = preparations[-1]
        first["on_state"]("loading")
        self.assertEqual(self.controller.snapshot.model_readiness, "loading")
        self.assertEqual(self.controller.snapshot.microphone_activity, "idle")
        self.controller.cancel()
        self.assertTrue(self.controller.prepare_model())
        first["on_state"]("ready")
        first["on_error"](RuntimeError("stale"))
        self.assertEqual(self.controller.snapshot.model_readiness, "loading")
        preparations[-1]["on_state"]("ready")
        self.assertEqual(self.controller.snapshot.model_readiness, "ready")
        self.assertIsNone(self.controller.snapshot.error)
        self.controller.apply_settings(replace(self.settings, model_path="/different"))
        self.assertEqual(self.controller.snapshot.model_readiness, "idle")

    def test_practice_rejects_model_preparation(self):
        self.assertTrue(hasattr(self.controller, "prepare_model"))
        calls = []
        self.audio.prepare = lambda *args, **kwargs: calls.append("model") or True
        practice = Controller(
            settings=self.settings,
            remote=PracticeInput(),
            audio=self.audio,
            schedule=self.scheduler.schedule,
            dispatch=lambda f: f(),
            practice=True,
        )
        self.assertFalse(practice.prepare_model())
        self.assertEqual(calls, [])

    def test_queued_draft_prepare_and_errors_cannot_affect_replacement(self):
        self.assertTrue(hasattr(self.controller, "prepare_model"))
        queued, preparations = [], []
        self.controller.dispatch = queued.append
        self.audio.prepare = lambda path, **kwargs: preparations.append(kwargs) or True
        self.controller.prepare_model()
        preparations[-1]["on_state"]("ready")
        preparations[-1]["on_error"](RuntimeError("late"))
        self.controller.cancel()
        self.assertTrue(self.controller.prepare_model())
        preparations[-1]["on_state"]("ready")
        while queued:
            queued.pop(0)()
        self.assertTrue(self.controller.start_recording())
        self.audio.callbacks["on_draft"]("private stale")
        self.controller.cancel()
        while queued:
            queued.pop(0)()
        self.assertEqual(self.controller.snapshot.draft_text, "")
        self.assertEqual(self.controller.snapshot.model_readiness, "idle")
        self.assertIsNone(self.controller.snapshot.error)

    def test_capture_loading_error_and_busy_start_do_not_leave_model_loading(self):
        self.controller.start_recording()
        self.audio.callbacks["on_error"](RuntimeError("model failed"))
        self.assertEqual(self.controller.snapshot.model_readiness, "error")
        self.controller.reset_error()
        self.audio.start = lambda *args, **kwargs: False
        self.assertFalse(self.controller.start_recording())
        self.assertEqual(self.controller.snapshot.model_readiness, "idle")

    def test_release_during_initial_load_can_report_model_ready_without_recording(self):
        self.controller.start_recording()
        self.controller.finish_recording()
        self.audio.callbacks["on_result"]("")
        self.assertEqual(self.controller.snapshot.model_readiness, "ready")
        self.assertEqual(self.controller.snapshot.draft_text, "")

    def test_completed_model_readiness_survives_cancel_but_settings_invalidate_it(self):
        preparations = []
        self.audio.prepare = lambda path, **kwargs: preparations.append(kwargs) or True
        self.controller.prepare_model()
        preparations[-1]["on_state"]("ready")
        self.controller.cancel()
        self.assertEqual(self.controller.snapshot.model_readiness, "ready")
        self.controller.stop()
        self.assertEqual(self.controller.snapshot.model_readiness, "ready")
        self.controller.apply_settings(self.settings)
        self.assertEqual(self.controller.snapshot.model_readiness, "idle")


class ControllerPortalLifecycleTests(unittest.TestCase):
    def make_controller(self, dispatch=lambda callback: callback()):
        from tests.test_portal import FakeTransport
        from wayland_voice_control.portal import GlobalShortcuts, RemoteDesktop

        self.wire = FakeTransport()
        self.remote = RemoteDesktop(self.wire, dispatch=dispatch)
        self.shortcuts = GlobalShortcuts(self.wire, lambda *_: None)
        self.audio = Audio()
        self.scheduler = Scheduler()
        self.controller = Controller(
            settings=replace(Settings(), microphone_consent=True, model_path="/model"),
            remote=self.remote,
            audio=self.audio,
            shortcuts=self.shortcuts,
            schedule=self.scheduler.schedule,
            dispatch=dispatch,
            clock=lambda: self.scheduler.now,
        )
        self.controller.prepare_model()

    def grant_keyboard(self):
        self.controller.connect()
        self.wire.reply({"session_handle": "/keyboard"})
        self.wire.reply()
        self.wire.reply({"devices": 1})

    def test_cancel_or_mode_change_closes_inflight_keyboard_session_at_each_stage(self):
        for stage in ("create", "select", "start"):
            for operation in ("cancel", "mode"):
                with self.subTest(stage=stage, operation=operation):
                    self.make_controller()
                    self.controller.connect()
                    if stage in ("select", "start"):
                        self.wire.reply({"session_handle": "/keyboard"})
                    if stage == "start":
                        self.wire.reply()
                    pending = self.wire.requests[-1]
                    if operation == "cancel":
                        self.controller.cancel()
                    else:
                        self.controller.set_mode(Mode.COMMANDS)
                    self.assertTrue(pending[6])
                    pending[5](
                        0,
                        {"session_handle": "/keyboard"}
                        if stage == "create"
                        else {"devices": 1},
                        None,
                    )
                    self.assertFalse(self.remote.granted)
                    self.assertFalse(self.controller.snapshot.permission_granted)
                    self.assertIn("/keyboard", self.wire.closed)
                    self.assertFalse(self.wire.signals)

    def test_cancel_closes_grant_whose_controller_callback_is_still_queued(self):
        queued = []
        self.make_controller(dispatch=queued.append)
        self.grant_keyboard()
        self.assertTrue(self.remote.granted)
        self.controller.cancel()
        while queued:
            queued.pop(0)()
        self.assertFalse(self.remote.granted)
        self.assertFalse(self.controller.snapshot.permission_granted)
        self.assertIn("/keyboard", self.wire.closed)

    def test_cancel_closes_inflight_shortcut_binding_and_late_session(self):
        for stage in ("create", "bind"):
            with self.subTest(stage=stage):
                self.make_controller()
                self.controller.connect_shortcuts()
                if stage == "bind":
                    self.wire.reply({"session_handle": "/shortcuts"})
                pending = self.wire.requests[-1]
                self.controller.cancel()
                self.assertTrue(pending[6])
                pending[5](
                    0,
                    {"session_handle": "/shortcuts"}
                    if stage == "create"
                    else {
                        "shortcuts": [("confirm", {"trigger_description": "Assigned"})]
                    },
                    None,
                )
                self.assertEqual(self.shortcuts.bindings, {})
                self.assertIn("/shortcuts", self.wire.closed)
                self.assertFalse(self.wire.signals)

    def test_shortcut_grant_is_reflected_when_recording_changes_action_generation(self):
        self.make_controller()
        self.grant_keyboard()
        snapshots = []
        self.controller.subscribe(snapshots.append)
        self.controller.connect_shortcuts()
        self.controller.start_recording()
        self.wire.reply({"session_handle": "/shortcuts"})
        self.wire.reply(
            {"shortcuts": [("confirm", {"trigger_description": "Assigned"})]}
        )
        self.assertEqual(snapshots[-1].shortcut_bindings, {"confirm": "Assigned"})
        self.assertEqual(snapshots[-1].state, State.RECORDING)

    def test_ordinary_cancel_keeps_completed_keyboard_and_shortcut_grants(self):
        self.make_controller()
        self.grant_keyboard()
        self.controller.connect_shortcuts()
        self.wire.reply({"session_handle": "/shortcuts"})
        self.wire.reply(
            {"shortcuts": [("confirm", {"trigger_description": "Assigned"})]}
        )
        self.controller.cancel()
        self.assertTrue(self.remote.granted)
        self.assertTrue(self.controller.snapshot.permission_granted)
        self.assertEqual(
            self.controller.snapshot.shortcut_bindings, {"confirm": "Assigned"}
        )
        self.assertEqual(self.wire.closed, [])

    def test_cancel_closes_shortcut_grant_queued_for_controller_delivery(self):
        queued = []
        self.make_controller(dispatch=queued.append)
        self.grant_keyboard()
        while queued:
            queued.pop(0)()
        self.controller.connect_shortcuts()
        self.wire.reply({"session_handle": "/shortcuts"})
        self.wire.reply(
            {"shortcuts": [("confirm", {"trigger_description": "Assigned"})]}
        )
        self.controller.cancel()
        while queued:
            queued.pop(0)()
        self.assertEqual(self.shortcuts.bindings, {})
        self.assertIn("/shortcuts", self.wire.closed)
        self.assertTrue(self.remote.granted)
        self.assertTrue(self.controller.snapshot.permission_granted)
