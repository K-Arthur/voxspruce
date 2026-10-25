"""The complete immutable command allowlist; no fuzzy matching or shell execution."""

from dataclasses import dataclass
from types import MappingProxyType

from .domain import DomainError, Risk


@dataclass(frozen=True, slots=True)
class Command:
    id: str
    phrase: str
    key_chord: str
    risk: Risk = Risk.NORMAL


COMMANDS = MappingProxyType(
    {
        command.id: command
        for command in (
            Command("next_field", "next field", "Tab"),
            Command("previous_field", "previous field", "Shift+Tab"),
            Command("copy", "copy", "Ctrl+C"),
            Command("paste", "paste", "Ctrl+V"),
            Command("undo", "undo", "Ctrl+Z"),
            Command("select_all", "select all", "Ctrl+A"),
            Command("press_enter", "press enter", "Return", Risk.HIGH),
            Command("close_window", "close window", "Alt+F4", Risk.HIGH),
            Command("delete_selection", "delete selection", "Delete", Risk.HIGH),
        )
    }
)


def match_command(transcript: str) -> Command:
    if isinstance(transcript, str):
        normalized = " ".join(transcript.casefold().split())
        for command in COMMANDS.values():
            if command.phrase == normalized:
                return command
    raise DomainError("Unknown command. Choose one command from the command list.")
