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

from .commands import command_catalogue
from .domain import DomainError, Mode, PendingAction, State, Workflow


@dataclass(frozen=True, slots=True)
class Snapshot:
    state: State
    pending: PendingAction | None
    status: str
    error: str | None
    microphone_activity: str
    draft_text: str
    model_readiness: str
    countdown_seconds: float
    permission_granted: bool
    microphone_consent: bool
    practice: bool
    shortcut_bindings: object
    commands: object
    custom_shortcuts: tuple
    edit_token: str | None
    practice_last_action: PendingAction | None


class PracticeInput:
    """Isolated no-op input boundary. It has no transport or desktop access."""

    granted = True

    def __init__(self):
        self.last_action = None

    def connect(self, callback, parent_window=""):
        self.granted = True
        callback(True, None)

    def execute(self, action, callback):
        self.last_action = action
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
        custom_shortcuts=None,
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
        self._custom_shortcuts = tuple(
            store.load_custom_shortcuts()
            if custom_shortcuts is None and store is not None
            else (() if custom_shortcuts is None else custom_shortcuts)
        )
        self._catalogue = command_catalogue(self._custom_shortcuts)
        self.mode = Mode.DICTATION
        self._thread = threading.get_ident()
        self._observers = []
        self._generation = 0
        self._connection_attempt = None
        self._shortcut_attempt = None
        self._timer = None
        self._deadline = None
        self._recording_id = None
        self._global_capture_started = False
        self._activity = "idle"
        self._draft = ""
        self._model_readiness = "idle"
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
            self.shortcuts.on_changed = self.shortcut_bindings_changed

    def _new_workflow(self):
        workflow = Workflow(
            confirmation_ttl_seconds=self.settings.confirmation_ttl_seconds,
            clock=self.clock,
        )
        workflow.set_custom_shortcuts(self._custom_shortcuts)
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
            self._draft,
            self._model_readiness,
            remaining,
            self._workflow.permission_granted,
            self.settings.microphone_consent,
            self.practice,
            MappingProxyType(dict(self.shortcuts.bindings))
            if self.shortcuts
            else MappingProxyType({}),
            self._catalogue,
            self._custom_shortcuts,
            self._workflow.edit_token,
            self.remote.last_action if self.practice else None,
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
        if snapshot.state is not State.RECORDING:
            self._global_capture_started = False
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
        if name == "show_controls" and not active:
            callback = getattr(self, "on_show_controls", None)
            if callback:
                callback()
        elif name == "hold_to_talk":
            if active and not self._global_capture_started:
                self._global_capture_started = bool(self.start_recording(self.mode))
            elif not active and self._global_capture_started:
                self._global_capture_started = False
                self.finish_recording()
        elif not active and name == "cancel":
            self.cancel()
        elif not active and name == "confirm" and self._workflow.pending:
            self.confirm(self._workflow.pending.id, source="global")

    def shortcut_bindings_changed(self, _keys):
        """Refresh assignments, invalidating held global and pending action work."""
        self._assert_thread()
        if self._global_capture_started or self._workflow.state in (
            State.PROCESSING,
            State.REVIEWING,
            State.EDITING,
            State.AWAITING_SECOND_CONFIRMATION,
            State.ARMED,
            State.EXECUTING,
        ):
            self.cancel()
        self._publish(
            "Global shortcuts changed. Release held shortcuts and press again; "
            "review a new action before confirming."
        )

    def prepare_model(self):
        """Explicit setup action: local model work only, no OS permissions."""
        self._assert_thread()
        if self.practice:
            self._publish(
                "Practice uses typed examples only; model loading is disabled."
            )
            return False
        self.cancel()
        generation = self._generation
        self._model_readiness = "loading"
        self._publish("Preparing local speech model…")

        def state(value):
            def apply():
                self._model_readiness = value
                self._publish(
                    {
                        "loading": "Preparing local speech model…",
                        "ready": "Local speech model ready.",
                        "error": "Local speech model preparation failed.",
                    }[value]
                )

            self._later(generation, apply)

        def failed(error):
            self._later(generation, lambda: self._fail(str(error)))

        try:
            if self.audio.prepare(
                self.settings.model_path, on_state=state, on_error=failed
            ):
                return True
            self._model_readiness = "idle"
            self._publish("Previous speech work is still stopping. Try again shortly.")
        except Exception as error:  # noqa: BLE001 - adapter errors must cancel safely
            self._model_readiness = "error"
            self._fail(str(error))
        return False

    def start_recording(self, mode=None):
        self._assert_thread()
        if self.practice:
            self._publish(
                "Practice uses typed examples only; the microphone stays off."
            )
            return False
        if self._model_readiness != "ready":
            self._publish("Prepare the local speech model in Setup before recording.")
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
        self._draft = ""
        self._model_readiness = "loading"
        self._publish("Loading local speech model…")

        def activity(value):
            def apply():
                self._activity = value
                if value == "recording":
                    self._model_readiness = "ready"
                if value in ("processing", "idle"):
                    self._draft = ""
                self._publish(
                    {
                        "loading": "Loading local speech model…",
                        "recording": "Recording while held…",
                        "processing": "Processing locally…",
                        "idle": "Recognition finished.",
                    }[value]
                )

            self._later(generation, apply)

        def draft(text):
            def apply():
                if self._workflow.state is State.RECORDING:
                    self._draft = text
                    self._publish()

            self._later(generation, apply)

        def result(text):
            def apply():
                self._draft = ""
                self._model_readiness = "ready"
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
                on_draft=draft,
            )
            if not started:
                self._model_readiness = "idle"
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
            self._draft = ""
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

    def begin_edit(self, action_id):
        """Call before the editor buffer changes; return an opaque edit token."""
        self._assert_thread()
        before = self._workflow.pending
        try:
            token = self._workflow.begin_edit(action_id)
        except DomainError as error:
            if self._workflow.pending is not before:
                self._generation += 1
                self._cancel_timer()
            self._publish(str(error))
            return None
        self._generation += 1
        self._cancel_timer()
        self._publish("Editing. Re-review the complete text before confirming.")
        return token

    def finish_edit(self, edit_token, text):
        self._assert_thread()
        try:
            self._workflow.finish_edit(edit_token, text)
        except DomainError as error:
            self._publish(str(error))
            return False
        self._publish("Edited. Review and confirm the new action.")
        return True

    def _activate_custom_shortcuts(self, items):
        catalogue = command_catalogue(items)
        self._custom_shortcuts, self._catalogue = tuple(items), catalogue
        self._workflow.set_custom_shortcuts(self._custom_shortcuts)
        self._publish(
            "Custom shortcuts updated. Review a new action before confirming."
        )
        return self._custom_shortcuts

    def replace_custom_shortcuts(self, items):
        """Explicit full replacement: validate, cancel, persist, then activate."""
        self._assert_thread()
        command_catalogue(items)
        items = tuple(items)
        self.cancel()
        if self.store is not None:
            items = self.store.replace_custom_shortcuts(items)
        return self._activate_custom_shortcuts(items)

    def _mutate_custom_shortcut(self, operation, *, item=None, identity=None):
        self._assert_thread()
        if operation != "delete":
            command_catalogue((item,))
            identity = item.id
        # Preflight against current configuration, rather than a potentially
        # stale controller snapshot. The store repeats validation under its
        # write lock, so concurrent writers cannot lose unrelated changes.
        current = (
            self.store.load_custom_shortcuts()
            if self.store is not None
            else self._custom_shortcuts
        )
        if operation == "add":
            proposed = (*current, item)
        else:
            if not any(entry.id == identity for entry in current):
                raise DomainError("Shortcut ID does not exist.")
            proposed = (
                tuple(item if entry.id == identity else entry for entry in current)
                if operation == "update"
                else tuple(entry for entry in current if entry.id != identity)
            )
        command_catalogue(proposed)
        self.cancel()
        if self.store is not None:
            if operation == "add":
                proposed = self.store.add_custom_shortcut(item)
            elif operation == "update":
                proposed = self.store.update_custom_shortcut(item)
            else:
                proposed = self.store.delete_custom_shortcut(identity)
        return self._activate_custom_shortcuts(proposed)

    def add_custom_shortcut(self, item):
        return self._mutate_custom_shortcut("add", item=item)

    def update_custom_shortcut(self, item):
        return self._mutate_custom_shortcut("update", item=item)

    def delete_custom_shortcut(self, identity):
        return self._mutate_custom_shortcut("delete", identity=identity)

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
        self._draft = ""
        if self._model_readiness == "loading":
            self._model_readiness = "error"
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
        self._draft = ""
        if self._model_readiness != "ready":
            self._model_readiness = "idle"
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
        self._model_readiness = "idle"
        self._workflow = self._new_workflow()
        if self.practice:
            self._workflow.set_permission(True)
        self._publish("Settings updated. Reconnect explicitly before live recording.")

    def update_settings(self, changes):
        self._assert_thread()
        if self.store is None:
            raise ValueError("No settings store was configured.")
        self.apply_settings(self.store.update(changes))

    def reset_settings(self):
        self._assert_thread()
        if self.store is None:
            raise ValueError("No settings store was configured.")
        self.stop()
        settings = self.store.reset()
        self._custom_shortcuts = ()
        self._catalogue = command_catalogue(())
        self.apply_settings(settings)
