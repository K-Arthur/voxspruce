import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from dataclasses import replace
from pathlib import Path

from wayland_voice_control.commands import CustomShortcut
from wayland_voice_control.storage import Settings, SettingsError, SettingsStore


class CustomStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "private" / "settings.db"
        self.store = SettingsStore(self.path)
        self.save = CustomShortcut("save", "save file", "Ctrl+S", "Save this file")

    def api(self):
        self.assertTrue(
            hasattr(self.store, "load_custom_shortcuts"),
            "Custom configuration storage missing",
        )

    def test_crud_is_validated_atomic_and_enabled_round_trips_as_bool(self):
        self.api()
        self.assertEqual(self.store.load_custom_shortcuts(), ())
        self.store.add_custom_shortcut(self.save)
        self.assertEqual(self.store.load_custom_shortcuts(), (self.save,))
        disabled = replace(self.save, enabled=False)
        self.store.update_custom_shortcut(disabled)
        self.assertIs(self.store.load_custom_shortcuts()[0].enabled, False)
        with self.assertRaises(SettingsError):
            self.store.add_custom_shortcut(replace(self.save, id="another"))
        with self.assertRaises(SettingsError):
            self.store.replace_custom_shortcuts((self.save, self.save))
        self.assertEqual(self.store.load_custom_shortcuts(), (disabled,))
        with self.assertRaises(SettingsError):
            self.store.update_custom_shortcut(replace(self.save, id="absent"))
        with self.assertRaises(SettingsError):
            self.store.delete_custom_shortcut("absent")
        self.store.delete_custom_shortcut("save")
        self.assertEqual(self.store.load_custom_shortcuts(), ())

    def test_v1_migration_preserves_every_preference_and_sets_database_version_two(
        self,
    ):
        self.path.parent.mkdir(mode=0o700)
        schema = (
            Path(__file__).resolve().parents[1] / "src/wayland_voice_control/schema.sql"
        ).read_text()
        # Construct the actual legacy schema, with no custom configuration table.
        settings_sql = schema[
            schema.index("CREATE TABLE settings") : schema.index("INSERT INTO settings")
        ]
        with closing(sqlite3.connect(self.path)) as db, db:
            db.executescript(settings_sql)
            db.execute(
                "INSERT INTO settings VALUES (1,1,'/models/local',1,45.5,7,55,'dark')"
            )
            db.execute("PRAGMA user_version=1")
        self.assertEqual(
            self.store.load(),
            Settings(
                model_path="/models/local",
                microphone_consent=True,
                confirmation_ttl_seconds=45.5,
                focus_delay_seconds=7,
                capture_limit_seconds=55,
                theme="dark",
            ),
        )
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 2)
        self.api()
        self.assertEqual(self.store.load_custom_shortcuts(), ())

    def test_migration_failure_leaves_legacy_bytes_and_version_unchanged(self):
        self.path.parent.mkdir(mode=0o700)
        schema = (
            Path(__file__).resolve().parents[1] / "src/wayland_voice_control/schema.sql"
        ).read_text()
        sql = schema[
            schema.index("CREATE TABLE settings") : schema.index("INSERT INTO settings")
        ]
        with closing(sqlite3.connect(self.path)) as db, db:
            db.executescript(sql)
            db.execute("INSERT INTO settings (id) VALUES (1)")
            db.execute("PRAGMA user_version=1")
            db.execute("CREATE TABLE custom_voice_shortcuts (unexpected TEXT)")
        original = self.path.read_bytes()
        with self.assertRaises(SettingsError):
            self.store.load()
        self.assertEqual(self.path.read_bytes(), original)

    def test_corrupt_custom_data_is_rejected_and_reset_clears_both_preferences_and_shortcuts(
        self,
    ):
        self.api()
        self.store.update({"theme": "dark"})
        self.store.add_custom_shortcut(self.save)
        settings, items = self.store.load_configuration()
        self.assertEqual(settings.theme, "dark")
        self.assertEqual(items, (self.save,))
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("PRAGMA ignore_check_constraints=ON")
            db.execute("UPDATE custom_voice_shortcuts SET key_chord='Ctrl+S;rm'")
        with self.assertRaises(SettingsError):
            self.store.load_custom_shortcuts()
        self.assertEqual(self.store.reset(), Settings())
        self.assertEqual(self.store.load_custom_shortcuts(), ())

    def test_json_schema_describes_custom_configuration_only(self):
        path = (
            Path(__file__).resolve().parents[1]
            / "schemas/custom-voice-shortcuts.schema.json"
        )
        self.assertTrue(path.exists(), "Custom shortcut JSON schema missing")
        schema = json.loads(path.read_text())
        self.assertEqual((schema["type"], schema["maxItems"]), ("array", 100))
        self.assertEqual(
            set(schema["items"]["required"]),
            {"id", "phrase", "key_chord", "description", "enabled"},
        )
        self.assertFalse(schema["items"]["additionalProperties"])
