"""The complete immutable command allowlist; no fuzzy matching or shell execution."""

import re
import unicodedata
from dataclasses import dataclass
from types import MappingProxyType

from .domain import DomainError, Risk


@dataclass(frozen=True, slots=True)
class Command:
    id: str
    phrase: str
    key_chord: str
    risk: Risk = Risk.NORMAL
    description: str = ""
    custom: bool = False


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


MODIFIERS = {"Ctrl": 0xFFE3, "Alt": 0xFFE9, "Shift": 0xFFE1, "Super": 0xFFEB}
BASE_KEYS = {
    "Space": 0x20,
    "Return": 0xFF0D,
    "Tab": 0xFF09,
    "Escape": 0xFF1B,
    "BackSpace": 0xFF08,
    "Delete": 0xFFFF,
    "Home": 0xFF50,
    "End": 0xFF57,
    "Left": 0xFF51,
    "Up": 0xFF52,
    "Right": 0xFF53,
    "Down": 0xFF54,
    "PageUp": 0xFF55,
    "PageDown": 0xFF56,
    **{f"F{i}": 0xFFBD + i for i in range(1, 13)},
    **{chr(i): ord(chr(i).lower()) for i in range(ord("A"), ord("Z") + 1)},
    **{str(i): ord(str(i)) for i in range(10)},
}


def parse_key_chord(value: str) -> tuple[str, tuple[int, ...]]:
    """Canonicalize exactly one allowlisted base key and distinct modifiers."""
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 64
        or not value.isascii()
    ):
        raise DomainError("Choose one supported keyboard shortcut chord.")
    parts = value.split("+")
    names = {name.casefold(): name for name in (*MODIFIERS, *BASE_KEYS)}
    try:
        tokens = [names[part.casefold()] for part in parts]
    except KeyError:
        raise DomainError("Unknown keyboard shortcut token.") from None
    if tokens[-1] not in BASE_KEYS or any(
        token not in MODIFIERS for token in tokens[:-1]
    ):
        raise DomainError("A shortcut needs one base key after its modifiers.")
    if len(set(tokens)) != len(tokens):
        raise DomainError("Shortcut modifiers cannot repeat.")
    ordered = [name for name in MODIFIERS if name in tokens[:-1]]
    return (
        "+".join([*ordered, tokens[-1]]),
        (*[MODIFIERS[name] for name in ordered], BASE_KEYS[tokens[-1]]),
    )


def _field(value, name, limit, *, blank=False):
    if (
        not isinstance(value, str)
        or len(value) > limit
        or (not blank and not value.strip())
        or any(
            unicodedata.category(char) in {"Cc", "Cf", "Cs", "Zl", "Zp"}
            for char in value
        )
    ):
        raise DomainError(f"{name} must be plain text of at most {limit} characters.")
    return value


@dataclass(frozen=True, slots=True)
class CustomShortcut:
    id: str
    phrase: str
    key_chord: str
    description: str = ""
    enabled: bool = True

    def __post_init__(self):
        if not isinstance(self.id, str) or not re.fullmatch(
            r"[A-Za-z0-9_-]{1,64}", self.id
        ):
            raise DomainError(
                "Shortcut ID must contain 1–64 ASCII letters, digits, underscores or hyphens."
            )
        phrase = _field(self.phrase, "Phrase", 120)
        object.__setattr__(
            self, "phrase", _field(" ".join(phrase.casefold().split()), "Phrase", 120)
        )
        object.__setattr__(self, "key_chord", parse_key_chord(self.key_chord)[0])
        _field(self.description, "Description", 240, blank=True)
        if type(self.enabled) is not bool:
            raise DomainError("Enabled must be a boolean.")


def command_catalogue(custom=()):
    """Validate all configuration, including disabled entries, before merging."""
    if not isinstance(custom, (tuple, list)) or len(custom) > 100:
        raise DomainError("Configure at most 100 custom shortcuts.")
    result = dict(COMMANDS)
    ids, phrases = set(result), {command.phrase for command in result.values()}
    for item in custom:
        if not isinstance(item, CustomShortcut):
            raise DomainError("Custom shortcuts must be validated configurations.")
        if item.id in ids or item.phrase in phrases:
            raise DomainError(
                "Shortcut IDs and phrases must be unique and cannot replace built-ins."
            )
        ids.add(item.id)
        phrases.add(item.phrase)
        if item.enabled:
            result[item.id] = Command(
                item.id, item.phrase, item.key_chord, Risk.HIGH, item.description, True
            )
    return MappingProxyType(result)


def match_command(transcript: str, catalogue=COMMANDS) -> Command:
    if isinstance(transcript, str):
        normalized = " ".join(transcript.casefold().split())
        for command in catalogue.values():
            if command.phrase == normalized:
                return command
    raise DomainError("Unknown command. Choose one command from the command list.")
