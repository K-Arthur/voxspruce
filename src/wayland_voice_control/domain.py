"""Pure validation and workflow rules; this module has no operating-system effects."""

import math
import time
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from uuid import uuid4


class DomainError(ValueError):
    """An action is invalid or no longer authorized."""


class Risk(str, Enum):
    NORMAL = "normal"
    HIGH = "high"


class Mode(str, Enum):
    DICTATION = "dictation"
    COMMANDS = "commands"


class ActionKind(str, Enum):
    TEXT = "text"
    COMMAND = "command"


class State(str, Enum):
    IDLE = "idle"
    RECORDING = "recording"
    PROCESSING = "processing"
    REVIEWING = "reviewing"
    EDITING = "editing"
    AWAITING_SECOND_CONFIRMATION = "awaiting_second_confirmation"
    ARMED = "armed"
    EXECUTING = "executing"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class PendingAction:
    id: str
    kind: ActionKind
    payload: str
    risk: Risk
    created_at: float
    expires_at: float
    key_chord: str | None = None
    phrase: str = ""
    description: str = ""
    custom: bool = False


def validate_dictation(text: str) -> str:
    """Accept literal text, never executable controls or multiline input."""
    if not isinstance(text, str) or not text.strip():
        raise DomainError("Dictation must contain text.")
    if len(text) > 4000:
        raise DomainError("Dictation is limited to 4000 characters.")
    if any(
        unicodedata.category(char) in {"Cc", "Cf", "Cs", "Zl", "Zp"} for char in text
    ):
        raise DomainError("Dictation cannot contain control or formatting characters.")
    return text


class Workflow:
    """Serialized UI workflow with no recording, persistence, or input injection.

    Call from one coordinator thread. Schedule delays while ARMED; call
    take_action only immediately before dispatching to the input adapter.
    The returned action is already consumed, including if the adapter fails.
    """

    def __init__(
        self,
        *,
        confirmation_ttl_seconds: float = 30,
        clock: Callable[[], float] = time.monotonic,
        id_factory: Callable[[], str] | None = None,
    ):
        if (
            isinstance(confirmation_ttl_seconds, bool)
            or not isinstance(confirmation_ttl_seconds, (int, float))
            or not 10 <= confirmation_ttl_seconds <= 120
            or not math.isfinite(confirmation_ttl_seconds)
        ):
            raise DomainError(
                "Confirmation lifetime must be between 10 and 120 seconds."
            )
        self._ttl = confirmation_ttl_seconds
        self._clock = clock
        self._id_factory = id_factory or (lambda: uuid4().hex)
        self._issued_ids: set[str] = set()
        from .commands import COMMANDS

        self._catalogue = COMMANDS
        self._edit_token: str | None = None
        self._permission = False
        self._microphone_consent = False
        self._state = State.IDLE
        self._pending: PendingAction | None = None
        self._mode: Mode | None = None
        self._recording_id: str | None = None
        self._error: str | None = None

    @property
    def state(self) -> State:
        return self._state

    @property
    def pending(self) -> PendingAction | None:
        return self._pending

    @property
    def edit_token(self) -> str | None:
        return self._edit_token

    @property
    def error(self) -> str | None:
        return self._error

    @property
    def permission_granted(self) -> bool:
        return self._permission

    @property
    def microphone_consent(self) -> bool:
        return self._microphone_consent

    def set_permission(self, granted: bool) -> None:
        if type(granted) is not bool:
            raise DomainError("Input permission must be a boolean.")
        self._permission = granted
        if not granted:
            self.cancel()

    def set_microphone_consent(self, granted: bool) -> None:
        if type(granted) is not bool:
            raise DomainError("Microphone consent must be a boolean.")
        self._microphone_consent = granted
        if not granted:
            self.cancel()

    def begin_recording(self, mode: Mode) -> str:
        self._require_gates()
        self._require_state(State.IDLE)
        if not isinstance(mode, Mode):
            raise DomainError("Choose Dictation or Commands explicitly.")
        recording_id = self._new_id()
        self._mode = mode
        self._recording_id = recording_id
        self._state = State.RECORDING
        return recording_id

    def finish_recording(self, recording_id: str) -> None:
        self._require_recording(recording_id, State.RECORDING)
        self._state = State.PROCESSING

    def receive_transcript(self, recording_id: str, text: str) -> PendingAction:
        self._require_recording(recording_id, State.PROCESSING)
        try:
            action = self._make_action(text)
        except DomainError as error:
            self.fail(str(error))
            raise
        self._pending = action
        self._recording_id = None
        self._state = State.REVIEWING
        return action

    def set_custom_shortcuts(self, custom) -> None:
        from .commands import command_catalogue

        catalogue = command_catalogue(custom)
        self.cancel()
        self._catalogue = catalogue

    def begin_edit(self, action_id: str) -> str:
        self._require_pending(
            action_id, State.REVIEWING, State.AWAITING_SECOND_CONFIRMATION, State.ARMED
        )
        token = self._new_id()
        self._pending = None
        self._edit_token = token
        self._state = State.EDITING
        return token

    def finish_edit(self, edit_token: str, text: str) -> PendingAction:
        self._require_gates()
        if self._edit_token is None or edit_token != self._edit_token:
            raise DomainError(
                "Stale edit identity. Continue editing the current draft."
            )
        self._require_state(State.EDITING)
        # Invalid intermediate buffers stay editable, with nothing executable.
        action = self._make_action(text)
        self._pending = action
        self._edit_token = None
        self._state = State.REVIEWING
        return action

    def edit_pending(self, action_id: str, text: str) -> PendingAction:
        self._require_pending(
            action_id, State.REVIEWING, State.AWAITING_SECOND_CONFIRMATION, State.ARMED
        )
        # Even an invalid edit must revoke the prior, potentially armed content.
        self._pending = None
        try:
            action = self._make_action(text)
        except DomainError as error:
            self.fail(str(error))
            raise
        self._pending = action
        self._state = State.REVIEWING
        return action

    def confirm(self, action_id: str) -> State:
        action = self._require_pending(action_id, State.REVIEWING)
        self._state = (
            State.AWAITING_SECOND_CONFIRMATION
            if action.risk is Risk.HIGH
            else State.ARMED
        )
        return self._state

    def confirm_second(self, action_id: str) -> State:
        self._require_pending(action_id, State.AWAITING_SECOND_CONFIRMATION)
        self._state = State.ARMED
        return self._state

    def take_action(self, action_id: str) -> PendingAction:
        """Consume approval once, immediately before the adapter sends input."""
        action = self._require_pending(action_id, State.ARMED)
        self._pending = None
        self._mode = None
        self._state = State.EXECUTING
        return action

    def complete_execution(self) -> None:
        self._require_state(State.EXECUTING)
        self.cancel()

    def cancel(self) -> None:
        self._edit_token = None
        self._pending = None
        self._recording_id = None
        self._mode = None
        self._error = None
        self._state = State.IDLE

    def stop(self) -> None:
        self.cancel()

    def reset(self) -> None:
        self.cancel()

    def disconnect(self) -> None:
        self.set_permission(False)

    def revoke_permission(self) -> None:
        self.set_permission(False)

    def fail(self, message: str) -> None:
        self.cancel()
        self._error = message
        self._state = State.ERROR

    def _require_gates(self) -> None:
        if not self._permission:
            raise DomainError("Input permission is required.")
        if not self._microphone_consent:
            raise DomainError("Microphone consent is required.")

    def _require_state(self, *states: State) -> None:
        if self._state not in states:
            raise DomainError(f"Action is unavailable while {self._state.value}.")

    def _require_recording(self, recording_id: str, state: State) -> None:
        self._require_gates()
        if self._recording_id is None or recording_id != self._recording_id:
            raise DomainError("Stale recording identity.")
        self._require_state(state)

    def _require_pending(self, action_id: str, *states: State) -> PendingAction:
        self._require_gates()
        action = self._pending
        if action is None or action.id != action_id:
            raise DomainError("Stale action identity. Review the current action.")
        if self._clock() >= action.expires_at:
            self.fail("The action expired. Record or review it again.")
            raise DomainError(self._error)
        self._require_state(*states)
        return action

    def _new_id(self) -> str:
        identity = self._id_factory()
        if (
            not isinstance(identity, str)
            or not identity
            or identity in self._issued_ids
        ):
            raise DomainError("Action identity must be unique and nonempty.")
        self._issued_ids.add(identity)
        return identity

    def _make_action(self, text: str) -> PendingAction:
        command = None
        if self._mode is Mode.DICTATION:
            kind, payload, risk = ActionKind.TEXT, validate_dictation(text), Risk.NORMAL
        else:
            from .commands import match_command

            command = match_command(text, self._catalogue)
            kind, payload, risk = ActionKind.COMMAND, command.id, command.risk
        now = self._clock()
        return PendingAction(
            self._new_id(),
            kind,
            payload,
            risk,
            now,
            now + self._ttl,
            command.key_chord if command else None,
            command.phrase if command else "",
            command.description if command else "",
            command.custom if command else False,
        )
