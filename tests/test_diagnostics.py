import tempfile
import unittest
from pathlib import Path

from wayland_voice_control.diagnostics import diagnose, read_settings
from wayland_voice_control.storage import SettingsStore


class DiagnosticsTests(unittest.TestCase):
    def test_missing_settings_stay_missing_and_no_permission_calls(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "absent" / "settings.db"
            calls = []
            report = diagnose(
                environment={
                    "XDG_SESSION_TYPE": "wayland",
                    "XDG_CURRENT_DESKTOP": "KDE",
                },
                settings_path=path,
                which=lambda name: "/bin/pw-record",
                dependency_probe=lambda: {
                    "gi": True,
                    "gtk4": True,
                    "adwaita": True,
                    "vosk": True,
                },
                portal_probe=lambda: (
                    calls.append(True)
                    or {
                        "remote_desktop": True,
                        "keyboard": True,
                        "global_shortcuts": True,
                    }
                ),
            )
            self.assertFalse(path.parent.exists())
            self.assertEqual(report["session_type"], "wayland")
            self.assertEqual(report["desktop"], "KDE")
            self.assertTrue(report["portal"]["keyboard"])
            self.assertFalse(report["model_exists"])
            self.assertEqual(calls, [True])

    def test_existing_settings_read_only_without_permission_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "private" / "settings.db"
            store = SettingsStore(path)
            expected = store.update({"model_path": directory})
            before = path.stat()
            actual = read_settings(path)
            self.assertEqual(actual, expected)
            self.assertEqual(path.stat().st_mtime_ns, before.st_mtime_ns)
            self.assertEqual(path.stat().st_mode, before.st_mode)

    def test_probe_failure_is_reported_without_hiding_other_diagnostics(self):
        def unavailable():
            raise RuntimeError("No session bus")

        with tempfile.TemporaryDirectory() as directory:
            report = diagnose(
                environment={},
                settings_path=Path(directory) / "absent.db",
                which=lambda name: None,
                dependency_probe=lambda: {"gi": False},
                portal_probe=unavailable,
            )
            self.assertEqual(report["portal"]["error"], "No session bus")
            self.assertIsNone(report["pw_record"])
