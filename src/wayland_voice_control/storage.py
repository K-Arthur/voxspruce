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

SCHEMA_VERSION = 1


class SettingsError(ValueError):
    """Settings are invalid, unsupported, or cannot be stored safely."""


@dataclass(frozen=True, slots=True)
class Settings:
    schema_version: int = SCHEMA_VERSION
    model_path: str = ""
    microphone_consent: bool = False
    confirmation_ttl_seconds: float = 30
    focus_delay_seconds: float = 3
    capture_limit_seconds: float = 30
    theme: str = "system"

    def __post_init__(self) -> None:
        if (
            type(self.schema_version) is not int
            or self.schema_version != SCHEMA_VERSION
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
        if version not in (0, SCHEMA_VERSION):
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
