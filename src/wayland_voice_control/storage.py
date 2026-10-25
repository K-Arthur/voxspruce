"""Validated SQLite settings only: no speech, transcript, action, or history data."""

import math
import os
import sqlite3
import stat
from collections.abc import Iterator, Mapping
from contextlib import closing, contextmanager
from dataclasses import asdict, dataclass, fields, replace
from importlib.resources import files
from pathlib import Path

from .commands import CustomShortcut, command_catalogue
from .domain import DomainError

SCHEMA_VERSION = 2
SETTINGS_SCHEMA_VERSION = 1


class SettingsError(ValueError):
    """Settings are invalid, unsupported, or cannot be stored safely."""


@dataclass(frozen=True, slots=True)
class Settings:
    schema_version: int = SETTINGS_SCHEMA_VERSION
    model_path: str = ""
    microphone_consent: bool = False
    confirmation_ttl_seconds: float = 30
    focus_delay_seconds: float = 3
    capture_limit_seconds: float = 30
    theme: str = "system"

    def __post_init__(self) -> None:
        if (
            type(self.schema_version) is not int
            or self.schema_version != SETTINGS_SCHEMA_VERSION
        ):
            raise SettingsError("Unsupported settings schema version.")
        if (
            not isinstance(self.model_path, str)
            or len(self.model_path) > 4096
            or "\0" in self.model_path
            or "://" in self.model_path
            or any(0xD800 <= ord(character) <= 0xDFFF for character in self.model_path)
        ):
            raise SettingsError(
                "Model path must be a local path string of at most 4096 characters."
            )
        if type(self.microphone_consent) is not bool:
            raise SettingsError("Microphone consent must be a boolean.")
        for name, minimum, maximum in (
            ("confirmation_ttl_seconds", 10, 120),
            ("focus_delay_seconds", 2, 10),
            ("capture_limit_seconds", 5, 60),
        ):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not minimum <= value <= maximum
                or not math.isfinite(value)
            ):
                raise SettingsError(
                    f"{name} must be a number between {minimum} and {maximum}."
                )
        if not isinstance(self.theme, str) or self.theme not in (
            "system",
            "light",
            "dark",
        ):
            raise SettingsError("Theme must be system, light, or dark.")


def default_settings_path(
    environment: Mapping[str, str] | None = None,
    *,
    home: Path | None = None,
) -> Path:
    environment = os.environ if environment is None else environment
    config_home = environment.get("XDG_CONFIG_HOME", "")
    base = (
        Path(config_home)
        if config_home and Path(config_home).is_absolute()
        else (home or Path.home()) / ".config"
    )
    return base / "wayland-voice-control" / "settings.db"


class SettingsStore:
    """Open short-lived transactions in an application-private directory.

    An explicit path's parent must already be private or be absent. Existing
    shared directories are never chmodded. Version checks precede file changes.
    """

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path is not None else default_settings_path()

    def load(self) -> Settings:
        with self._connection() as connection:
            return self._read(connection)

    def load_configuration(self) -> tuple[Settings, tuple[CustomShortcut, ...]]:
        with self._connection() as connection, connection:
            connection.execute("BEGIN")
            return self._read(connection), self._read_custom(connection)

    def load_custom_shortcuts(self) -> tuple[CustomShortcut, ...]:
        with self._connection() as connection:
            return self._read_custom(connection)

    @staticmethod
    def _validate_custom(items):
        try:
            command_catalogue(items)
        except DomainError as error:
            raise SettingsError(str(error)) from error
        return tuple(items)

    @classmethod
    def _read_custom(cls, connection):
        try:
            rows = connection.execute(
                "SELECT id, phrase, key_chord, description, enabled FROM custom_voice_shortcuts ORDER BY rowid"
            ).fetchall()
            items = []
            for row in rows:
                values = dict(row)
                enabled = values["enabled"]
                if type(enabled) is not int or enabled not in (0, 1):
                    raise SettingsError("Stored shortcut enabled flag is invalid.")
                values["enabled"] = bool(enabled)
                item = CustomShortcut(**values)
                if (
                    item.phrase != values["phrase"]
                    or item.key_chord != values["key_chord"]
                ):
                    raise SettingsError("Stored shortcut must be canonical.")
                items.append(item)
            return cls._validate_custom(items)
        except DomainError as error:
            raise SettingsError(str(error)) from error

    @staticmethod
    def _write_custom(connection, items):
        connection.execute("DELETE FROM custom_voice_shortcuts")
        connection.executemany(
            "INSERT INTO custom_voice_shortcuts (id, phrase, key_chord, description, enabled) VALUES (?, ?, ?, ?, ?)",
            [
                (item.id, item.phrase, item.key_chord, item.description, item.enabled)
                for item in items
            ],
        )

    def replace_custom_shortcuts(self, items) -> tuple[CustomShortcut, ...]:
        items = self._validate_custom(items)
        with self._connection() as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            self._write_custom(connection, items)
        return items

    def _mutate_custom(self, item=None, *, identity=None, add=False):
        if item is not None:
            self._validate_custom((item,))
            identity = item.id
        with self._connection() as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            items = list(self._read_custom(connection))
            found = next(
                (
                    index
                    for index, current in enumerate(items)
                    if current.id == identity
                ),
                None,
            )
            if add:
                if found is not None:
                    raise SettingsError("Shortcut ID already exists.")
                items.append(item)
            else:
                if found is None:
                    raise SettingsError("Shortcut ID does not exist.")
                if item is None:
                    del items[found]
                else:
                    items[found] = item
            result = self._validate_custom(items)
            self._write_custom(connection, result)
            return result

    def add_custom_shortcut(self, item) -> tuple[CustomShortcut, ...]:
        return self._mutate_custom(item, add=True)

    def update_custom_shortcut(self, item) -> tuple[CustomShortcut, ...]:
        return self._mutate_custom(item)

    def delete_custom_shortcut(self, identity: str) -> tuple[CustomShortcut, ...]:
        return self._mutate_custom(identity=identity)

    def update(self, changes: Mapping[str, object]) -> Settings:
        if not isinstance(changes, Mapping):
            raise SettingsError("Settings changes must be a mapping.")
        allowed = {field.name for field in fields(Settings)}
        if any(name not in allowed for name in changes):
            raise SettingsError("Unknown settings field.")
        with self._connection() as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            settings = replace(self._read(connection), **changes)
            self._write(connection, settings)
            return settings

    def reset(self) -> Settings:
        with self._connection() as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            settings = Settings()
            self._write_custom(connection, ())
            self._write(connection, settings)
            return settings

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = None
        try:
            if self.path.is_symlink() or self.path.parent.is_symlink():
                raise SettingsError(
                    "Settings database and directory cannot be symbolic links."
                )
            # Do not tighten permissions or mutate a database from a newer app.
            if self.path.exists():
                with closing(
                    sqlite3.connect(
                        self.path.absolute().as_uri() + "?mode=ro", uri=True
                    )
                ) as probe:
                    self._check_version(probe)
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            if stat.S_IMODE(self.path.parent.stat().st_mode) & 0o077:
                raise SettingsError(
                    "Settings directory must be private (0700). Choose a private subdirectory."
                )
            try:
                descriptor = os.open(
                    self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
                )
            except FileExistsError:
                pass
            else:
                os.close(descriptor)
            connection = sqlite3.connect(self.path)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            version = self._check_version(connection)
            if version == 0:
                tables = connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
                if tables:
                    raise SettingsError(
                        "Unrecognized settings schema version; no migration is available."
                    )
                connection.executescript(
                    files("wayland_voice_control")
                    .joinpath("schema.sql")
                    .read_text(encoding="utf-8")
                )
            elif version == 1:
                # CREATE and version advance commit together; validate legacy
                # preferences before migration and never rewrite their values.
                with connection:
                    connection.execute("BEGIN IMMEDIATE")
                    self._read(connection)
                    connection.execute(
                        files("wayland_voice_control")
                        .joinpath("custom-shortcuts.sql")
                        .read_text(encoding="utf-8")
                    )
                    connection.execute("PRAGMA user_version = 2")
            os.chmod(self.path, 0o600)
            yield connection
        except (sqlite3.Error, OSError) as error:
            raise SettingsError(
                "The settings database could not be read or written safely."
            ) from error
        finally:
            if connection is not None:
                connection.close()

    @staticmethod
    def _check_version(connection: sqlite3.Connection) -> int:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        if version not in (0, 1, SCHEMA_VERSION):
            raise SettingsError(
                "Unsupported or newer settings schema version. The database was not changed."
            )
        return version

    @staticmethod
    def _read(connection: sqlite3.Connection) -> Settings:
        columns = ", ".join(field.name for field in fields(Settings))
        row = connection.execute(
            f"SELECT {columns} FROM settings WHERE id = 1"
        ).fetchone()
        if row is None:
            raise SettingsError("Settings are missing. Reset settings to recover.")
        values = dict(row)
        consent = values["microphone_consent"]
        if type(consent) is not int or consent not in (0, 1):
            raise SettingsError("Stored microphone consent is invalid.")
        values["microphone_consent"] = bool(consent)
        return Settings(**values)

    @staticmethod
    def _write(connection: sqlite3.Connection, settings: Settings) -> None:
        values = asdict(settings)
        columns = ", ".join(values)
        placeholders = ", ".join("?" for _ in values)
        # Only dataclass field names enter SQL. All setting values are bound.
        connection.execute(
            f"INSERT OR REPLACE INTO settings (id, {columns}) VALUES (1, {placeholders})",
            tuple(values.values()),
        )
