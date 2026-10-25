import unittest
from dataclasses import replace

from wayland_voice_control.controller import Controller, PracticeInput
from wayland_voice_control.domain import Mode, State
from wayland_voice_control.storage import Settings


class Audio:
    def __init__(self):
        self.callbacks = {}
        self.cancelled = 0

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
        self.controller.connect()
        self.remote.grant()

    def review(self, text="hello", mode=Mode.DICTATION):
        self.controller.start_recording(mode)
        self.audio.callbacks["on_activity"]("recording")
        self.controller.finish_recording()
        self.audio.callbacks["on_result"](text)
        return self.controller.snapshot.pending.id

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
