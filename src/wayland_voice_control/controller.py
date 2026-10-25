"""Serialized coordinator for native UI and injectable operating-system adapters.

Call public methods on the creating/UI thread. Worker completions are dispatched
there before touching Workflow. Every asynchronous success AND failure checks its
operation identity: Workflow.fail/complete_execution do not carry identities.
Observers receive immutable snapshots. No method sends unreviewed live text.
"""

import threading
import time
from dataclasses import dataclass
from types import MappingProxyType

from .domain import DomainError, Mode, PendingAction, State, Workflow


@dataclass(frozen=True, slots=True)
class Snapshot:
    state: State
    pending: PendingAction | None
    status: str
    error: str | None
    microphone_activity: str
    countdown_seconds: float
    permission_granted: bool
    microphone_consent: bool
    practice: bool
    shortcut_bindings: object


class PracticeInput:
    """Isolated no-op input boundary. It has no transport or desktop access."""

    granted = True

    def connect(self, callback, parent_window=""):
        self.granted = True
        callback(True, None)

    def execute(self, action, callback):
        callback(None)

    def cancel_input(self):
        pass

    def close(self):
        self.granted = False


class Controller:
    def __init__(
        self,
        *,
        settings,
        remote,
        audio,
        schedule,
        dispatch,
        store=None,
        shortcuts=None,
        clock=time.monotonic,
        practice=False,
    ):
        if practice and not isinstance(remote, PracticeInput):
            raise ValueError("Practice requires an isolated PracticeInput adapter.")
        self.settings, self.remote, self.audio = settings, remote, audio
        self.schedule, self.dispatch, self.clock = schedule, dispatch, clock
        self.store, self.shortcuts, self.practice = (
            store,
            (None if practice else shortcuts),
            practice,
        )
        self.mode = Mode.DICTATION
        self._thread = threading.get_ident()
        self._observers = []
        self._generation = 0
        self._connection_attempt = None
        self._shortcut_attempt = None
        self._timer = None
        self._deadline = None
        self._recording_id = None
        self._activity = "idle"
        self._status = (
            "Practice: input will be simulated."
            if practice
            else "Ready. Request keyboard access to begin."
        )
        self._workflow = self._new_workflow()
        self._workflow.set_permission(bool(remote.granted))
        # Portal session callbacks are already UI-dispatched by Gio.
        remote.on_closed = self.permission_lost
        if self.shortcuts:
            self.shortcuts.on_event = self.shortcut_event
            self.shortcuts.on_closed = self.cancel

    def _new_workflow(self):
        workflow = Workflow(
            confirmation_ttl_seconds=self.settings.confirmation_ttl_seconds,
            clock=self.clock,
        )
        workflow.set_microphone_consent(
            self.settings.microphone_consent or self.practice
        )
        return workflow

    def _assert_thread(self):
        if threading.get_ident() != self._thread:
            raise RuntimeError(
                "Controller methods must run on the UI dispatcher thread."
            )

    @property
    def snapshot(self):
        remaining = (
            max(0, self._deadline - self.clock()) if self._deadline is not None else 0
        )
        return Snapshot(
            self._workflow.state,
            self._workflow.pending,
            self._status,
            self._workflow.error,
            self._activity,
            remaining,
            self._workflow.permission_granted,
            self.settings.microphone_consent,
            self.practice,
            MappingProxyType(dict(self.shortcuts.bindings))
            if self.shortcuts
            else MappingProxyType({}),
        )

    def subscribe(self, callback):
        self._assert_thread()
        self._observers.append(callback)
        callback(self.snapshot)

        def unsubscribe():
            if callback in self._observers:
                self._observers.remove(callback)

        return unsubscribe

    def _publish(self, status=None):
        self._assert_thread()
        if status is not None:
            self._status = status
        snapshot = self.snapshot
        for callback in tuple(self._observers):
            callback(snapshot)

    def _later(self, generation, callback):
        def guarded():
            self._assert_thread()
            if generation == self._generation:
                callback()

        self.dispatch(guarded)

    def connect(self, parent_window=""):
        self._assert_thread()
        self.cancel()
        self._workflow.set_permission(False)
        attempt = self._connection_attempt = object()
        self._publish("Waiting for desktop keyboard permission…")

        def complete(granted, error):
            def apply():
                self._assert_thread()
                if self._connection_attempt is not attempt:
                    return
                self._connection_attempt = None
                self._workflow.set_permission(bool(granted))
                self._publish(
                    "Keyboard permission granted."
                    if granted
                    else f"Keyboard access unavailable: {error}"
                )

            self.dispatch(apply)

        if self._connection_attempt is attempt:
            self.remote.connect(complete, parent_window)

    def connect_shortcuts(self, parent_window=""):
        self._assert_thread()
        if self.shortcuts:
            attempt = self._shortcut_attempt = object()

            def complete(granted, error):
                def apply():
                    self._assert_thread()
                    if self._shortcut_attempt is not attempt:
                        return
                    self._shortcut_attempt = None
                    self._publish(
                        "Global shortcuts ready."
                        if granted
                        else f"Global shortcuts unavailable; use local controls. {error}"
                    )

                self.dispatch(apply)

            self.shortcuts.connect(complete, parent_window)

    def set_mode(self, mode):
        self._assert_thread()
        if not isinstance(mode, Mode):
            raise TypeError("Choose Dictation or Commands.")
        if mode is not self.mode:
            self.cancel()
            self.mode = mode
            self._publish(f"{mode.value.capitalize()} mode selected.")

    def shortcut_event(self, name, active):
        self._assert_thread()
        if name == "hold_to_talk":
            self.start_recording(self.mode) if active else self.finish_recording()
        elif not active and name == "cancel":
            self.cancel()
        elif not active and name == "confirm" and self._workflow.pending:
            self.confirm(self._workflow.pending.id, source="global")

    def start_recording(self, mode=None):
        self._assert_thread()
        if self.practice:
            self._publish(
                "Practice uses typed examples only; the microphone stays off."
            )
            return False
        try:
            recording_id = self._workflow.begin_recording(
                self.mode if mode is None else mode
            )
        except DomainError as error:
            self._publish(str(error))
            return False
        self._generation += 1
        generation = self._generation
        self._recording_id = recording_id
        self._publish("Loading local speech model…")

        def activity(value):
            def apply():
                self._activity = value
                self._publish(
                    {
                        "loading": "Loading local speech model…",
                        "recording": "Recording while held…",
                        "processing": "Processing locally…",
                        "idle": "Recognition finished.",
                    }[value]
                )

            self._later(generation, apply)

        def result(text):
            def apply():
                if self._workflow.state is State.RECORDING:
                    self._workflow.finish_recording(recording_id)
                try:
                    self._workflow.receive_transcript(recording_id, text)
                except DomainError as error:
                    self._publish(str(error))
                else:
                    self._publish("Review the recognized action before confirming.")
                self._recording_id = None

            self._later(generation, apply)

        def failed(error):
            self._later(generation, lambda: self._fail(f"Capture failed: {error}"))

        try:
            started = self.audio.start(
                self.settings.model_path,
                consent=self.settings.microphone_consent,
                limit=self.settings.capture_limit_seconds,
                on_activity=activity,
                on_result=result,
                on_error=failed,
            )
            if not started:
                self._workflow.cancel()
                self._recording_id = None
                self._publish(
                    "The previous capture is still stopping. Try again shortly."
                )
                return False
        except Exception as error:  # noqa: BLE001 - adapter failures must cancel safely
            self._fail(str(error))
            return False
        return True

    def finish_recording(self):
        self._assert_thread()
        if self._workflow.state is State.RECORDING and self._recording_id:
            self._workflow.finish_recording(self._recording_id)
            self.audio.stop()
            self._publish("Processing locally…")

    def review_text(self, text, mode=Mode.DICTATION):
        """Typed practice examples only; live actions enter via capture callbacks."""
        self._assert_thread()
        if not self.practice or not isinstance(self.remote, PracticeInput):
            raise ValueError("Typed examples are restricted to isolated practice mode.")
        self.cancel()
        self._workflow.set_permission(True)
        identity = self._workflow.begin_recording(mode)
        self._workflow.finish_recording(identity)
        try:
            self._workflow.receive_transcript(identity, text)
        except DomainError as error:
            self._publish(str(error))
            return False
        self._publish("Practice: review and confirm this simulated action.")
        return True

    def edit(self, action_id, text):
        self._assert_thread()
        prior_state, prior_pending = self._workflow.state, self._workflow.pending
        try:
            self._workflow.edit_pending(action_id, text)
        except DomainError as error:
            # Stale identities and invalid-state events do not change Workflow:
            # they must not orphan the current capture, countdown or execution.
            # Invalid content/expiry does change it and revokes existing work.
            if (
                self._workflow.state is not prior_state
                or self._workflow.pending is not prior_pending
            ):
                self._generation += 1
                self._cancel_timer()
            self._publish(str(error))
            return False
        self._generation += 1
        self._cancel_timer()
        self._publish("Edited. Review and confirm the new action.")
        return True

    def confirm(self, action_id, *, source="local"):
        self._assert_thread()
        try:
            state = self._workflow.confirm(action_id)
        except DomainError as error:
            self._publish(str(error))
            return False
        if state is State.ARMED:
            self._arm(action_id, source)
        else:
            self._publish(
                "This command can submit or destroy content. Use the separate second confirmation."
            )
        return True

    def confirm_second(self, action_id, *, source="local"):
        """Separate UI action; the global first-confirm shortcut never calls this."""
        self._assert_thread()
        try:
            self._workflow.confirm_second(action_id)
        except DomainError as error:
            self._publish(str(error))
            return False
        self._arm(action_id, source)
        return True

    def _arm(self, action_id, source):
        self._cancel_timer()
        delay = 0.15 if source == "global" else self.settings.focus_delay_seconds
        self._deadline = self.clock() + delay
        generation = self._generation
        self._publish("Choose the destination field. Input begins after the countdown.")

        def tick():
            self._timer = None
            if generation != self._generation:
                return
            remaining = self._deadline - self.clock()
            if remaining > 0:
                self._publish()
                self._timer = self.schedule(min(1, remaining), tick)
                return
            self._deadline = None
            try:
                action = self._workflow.take_action(action_id)
            except DomainError as error:
                self._publish(str(error))
                return
            self._publish("Sending the approved action…")

            def completed(error):
                def apply():
                    # Both paths require the generation gate; these Workflow
                    # methods are deliberately untagged and must never run late.
                    if self._workflow.state is not State.EXECUTING:
                        return
                    if error:
                        self._fail(
                            "Input may have been partially sent. It will not be retried. "
                            "Check the destination before starting again. " + str(error)
                        )
                    else:
                        self._workflow.complete_execution()
                        self._publish(
                            "Practice complete; no desktop input was sent."
                            if self.practice
                            else "Approved action sent."
                        )

                self._later(generation, apply)

            try:
                self.remote.execute(action, completed)
            except Exception as error:  # noqa: BLE001 - adapter failures must cancel safely
                completed(error)

        self._timer = self.schedule(min(1, delay), tick)

    def _cancel_timer(self):
        if self._timer:
            self._timer()
        self._timer = self._deadline = None

    def _fail(self, message):
        self._workflow.fail(message)
        self._activity = "idle"
        self._recording_id = None
        self._publish(message)

    def cancel(self):
        self._assert_thread()
        self._generation += 1
        self._cancel_timer()
        # Permission attempts have identities separate from action generations.
        # Cancel must close pending grants, including responses queued for UI
        # delivery; completed permissions may remain until explicit stop/revoke.
        if self._connection_attempt is not None:
            self._connection_attempt = None
            self.remote.close()
            self._workflow.set_permission(False)
        if self._shortcut_attempt is not None:
            self._shortcut_attempt = None
            self.shortcuts.close()
        if not self.practice:
            self.audio.cancel()
        self.remote.cancel_input()
        self._workflow.cancel()
        self._recording_id = None
        self._activity = "idle"
        self._publish("Cancelled. Pending content discarded.")

    def stop(self):
        self._assert_thread()
        self.cancel()
        self.remote.close()
        if self.shortcuts:
            self.shortcuts.close()
        self._workflow.set_permission(False)
        self._publish(
            "Stopped. Keyboard permission closed; reconnect explicitly to continue."
        )

    def permission_lost(self):
        self._assert_thread()
        self.stop()
        self._publish("Desktop keyboard permission ended. Pending content discarded.")

    def reset_error(self):
        self._assert_thread()
        if self._workflow.state is State.ERROR:
            self.cancel()
            self._publish("Error cleared. Ready for a new recording.")

    def apply_settings(self, settings):
        """Apply already-validated Settings, cancelling and revoking current work."""
        self._assert_thread()
        self.stop()
        self.settings = settings
        self._workflow = self._new_workflow()
        if self.practice:
            self._workflow.set_permission(True)
        self._publish("Settings updated. Reconnect explicitly before live recording.")

    def update_settings(self, changes):
        if self.store is None:
            raise ValueError("No settings store was configured.")
        self.apply_settings(self.store.update(changes))

    def reset_settings(self):
        if self.store is None:
            raise ValueError("No settings store was configured.")
        self.apply_settings(self.store.reset())
