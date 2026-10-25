import dataclasses
import json
import os
import sqlite3
import stat
import tempfile
import unittest
from pathlib import Path

from tests import require_module


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.storage = require_module(self, "wayland_voice_control.storage")
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "private" / "settings.db"
        self.store = self.storage.SettingsStore(self.path)

    def test_defaults_are_safe_and_round_trip(self):
        settings = self.store.load()
        self.assertEqual(
            dataclasses.asdict(settings),
            {
                "schema_version": 1,
                "model_path": "",
                "microphone_consent": False,
                "confirmation_ttl_seconds": 30,
                "focus_delay_seconds": 3,
                "capture_limit_seconds": 30,
                "theme": "system",
            },
        )
        self.assertEqual(self.storage.SettingsStore(self.path).load(), settings)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            settings.microphone_consent = True

    def test_updates_round_trip_and_do_not_require_an_existing_model(self):
        changes = {
            "model_path": "/not-installed-yet/model",
            "microphone_consent": True,
            "confirmation_ttl_seconds": 45.5,
            "focus_delay_seconds": 2,
            "capture_limit_seconds": 60,
            "theme": "dark",
        }
        updated = self.store.update(changes)
        self.assertEqual(self.store.load(), updated)
        for name, value in changes.items():
            self.assertEqual(getattr(updated, name), value)

    def test_invalid_update_is_atomic(self):
        original = self.store.update({"theme": "light"})
        with self.assertRaises(self.storage.SettingsError):
            self.store.update({"theme": "dark", "capture_limit_seconds": 61})
        self.assertEqual(self.store.load(), original)

    def test_unknown_settings_are_rejected(self):
        for changes in (
            {"transcript": "secret"},
            {"shell_command": "echo hello"},
            {"schema_version": 2},
        ):
            with (
                self.subTest(changes=changes),
                self.assertRaises(self.storage.SettingsError),
            ):
                self.store.update(changes)

    def test_boolean_and_numeric_types_are_validated_separately(self):
        for value in (1, 0, "true", None):
            with (
                self.subTest(value=value),
                self.assertRaises(self.storage.SettingsError),
            ):
                self.store.update({"microphone_consent": value})
        for name in (
            "confirmation_ttl_seconds",
            "focus_delay_seconds",
            "capture_limit_seconds",
        ):
            for value in (
                True,
                False,
                10**1000,
                float("nan"),
                float("inf"),
                -float("inf"),
                "30",
                None,
            ):
                with (
                    self.subTest(name=name, value=value),
                    self.assertRaises(self.storage.SettingsError),
                ):
                    self.store.update({name: value})

    def test_numeric_ranges_include_the_documented_boundaries(self):
        for name, minimum, maximum in (
            ("confirmation_ttl_seconds", 10, 120),
            ("focus_delay_seconds", 2, 10),
            ("capture_limit_seconds", 5, 60),
        ):
            for value in (minimum, maximum):
                with self.subTest(name=name, value=value):
                    self.assertEqual(
                        getattr(self.store.update({name: value}), name), value
                    )
            for value in (minimum - 0.1, maximum + 0.1):
                with (
                    self.subTest(name=name, value=value),
                    self.assertRaises(self.storage.SettingsError),
                ):
                    self.store.update({name: value})

    def test_paths_and_themes_are_validated(self):
        for value in (
            None,
            12,
            True,
            Path("model"),
            "model\0path",
            "\ud800",
            "x" * 4097,
            "https://example.com/model",
        ):
            with (
                self.subTest(value=repr(value)),
                self.assertRaises(self.storage.SettingsError),
            ):
                self.store.update({"model_path": value})
        for value in ("auto", "DARK", True, None):
            with (
                self.subTest(value=value),
                self.assertRaises(self.storage.SettingsError),
            ):
                self.store.update({"theme": value})

    def test_reset_restores_defaults_without_keeping_a_history(self):
        self.store.update(
            {"microphone_consent": True, "theme": "dark", "model_path": "/old/model"}
        )
        self.assertEqual(self.store.reset(), self.storage.Settings())
        self.assertEqual(self.store.load(), self.storage.Settings())
        with sqlite3.connect(self.path) as connection:
            self.assertEqual(
                connection.execute("SELECT count(*) FROM settings").fetchone()[0], 1
            )

    def test_corrupt_stored_values_fail_validation_and_reset_can_repair_them(self):
        self.store.load()
        with sqlite3.connect(self.path) as connection:
            connection.execute("PRAGMA ignore_check_constraints = ON")
            connection.execute("UPDATE settings SET theme='unexpected'")
        with self.assertRaises(self.storage.SettingsError):
            self.store.load()
        self.assertEqual(self.store.reset(), self.storage.Settings())

    def test_future_schema_fails_without_changing_file_or_permissions(self):
        self.store.load()
        with sqlite3.connect(self.path) as connection:
            connection.execute("PRAGMA user_version = 99")
        os.chmod(self.path, 0o640)
        original = self.path.read_bytes()
        original_mode = stat.S_IMODE(self.path.stat().st_mode)
        for operation in (
            self.store.load,
            self.store.reset,
            lambda: self.store.update({"theme": "dark"}),
        ):
            with self.assertRaisesRegex(
                self.storage.SettingsError, "newer|future|version"
            ):
                operation()
            self.assertEqual(self.path.read_bytes(), original)
            self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), original_mode)

    def test_database_has_only_settings_columns_and_a_version(self):
        self.store.load()
        with sqlite3.connect(self.path) as connection:
            tables = connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            self.assertEqual(tables, [("settings",), ("custom_voice_shortcuts",)])
            columns = {
                row[1] for row in connection.execute("PRAGMA table_info(settings)")
            }
            self.assertEqual(
                columns, set(dataclasses.asdict(self.storage.Settings())) | {"id"}
            )
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 2)

    def test_created_database_and_directory_are_private(self):
        self.store.load()
        self.assertEqual(stat.S_IMODE(self.path.parent.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)

    def test_symlink_database_is_rejected_without_mutating_target(self):
        target = Path(self.temporary.name) / "target.db"
        target.write_text("do not change")
        self.path.parent.mkdir(mode=0o700)
        self.path.symlink_to(target)
        with self.assertRaises(self.storage.SettingsError):
            self.store.load()
        self.assertEqual(target.read_text(), "do not change")

    def test_shared_existing_parent_is_rejected_without_chmod(self):
        self.path.parent.mkdir(mode=0o755)
        os.chmod(self.path.parent, 0o755)
        with self.assertRaises(self.storage.SettingsError):
            self.store.load()
        self.assertEqual(stat.S_IMODE(self.path.parent.stat().st_mode), 0o755)

    def test_xdg_path_and_home_fallback(self):
        self.assertEqual(
            self.storage.default_settings_path(
                {"XDG_CONFIG_HOME": "/custom/config"}, home=Path("/home/test")
            ),
            Path("/custom/config/wayland-voice-control/settings.db"),
        )
        for environment in (
            {},
            {"XDG_CONFIG_HOME": "relative/path"},
            {"XDG_CONFIG_HOME": ""},
        ):
            self.assertEqual(
                self.storage.default_settings_path(
                    environment, home=Path("/home/test")
                ),
                Path("/home/test/.config/wayland-voice-control/settings.db"),
            )

    def test_json_schema_matches_defaults_types_ranges_and_closed_fields(self):
        schema_path = (
            Path(__file__).resolve().parents[1] / "schemas" / "settings.schema.json"
        )
        self.assertTrue(schema_path.exists(), "Settings schema must be supplied")
        schema = json.loads(schema_path.read_text())
        defaults = dataclasses.asdict(self.storage.Settings())
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(set(schema["properties"]), set(defaults))
        self.assertEqual(set(schema["required"]), set(defaults))
        for name, value in defaults.items():
            self.assertEqual(schema["properties"][name]["default"], value)
        self.assertEqual(schema["properties"]["microphone_consent"]["type"], "boolean")
        for name, limits in (
            ("confirmation_ttl_seconds", (10, 120)),
            ("focus_delay_seconds", (2, 10)),
            ("capture_limit_seconds", (5, 60)),
        ):
            self.assertEqual(
                (
                    schema["properties"][name]["minimum"],
                    schema["properties"][name]["maximum"],
                ),
                limits,
            )


if __name__ == "__main__":
    unittest.main()
