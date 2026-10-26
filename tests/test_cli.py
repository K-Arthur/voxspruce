import contextlib
import io
import json
import subprocess
import sys
import types
import unittest
from unittest.mock import patch

from wayland_voice_control.__main__ import main


class CliTests(unittest.TestCase):
    def test_help_without_loading_gtk_or_app(self):
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                """
import sys
from wayland_voice_control.__main__ import main
try:
    main(["--help"])
except SystemExit as error:
    assert error.code == 0
assert "wayland_voice_control.app" not in sys.modules
assert "gi" not in sys.modules
""",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("doctor", result.stdout)

    def test_commands_shows_risks_and_exact_phrases(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(["commands"]), 0)
        self.assertIn("press enter", output.getvalue())
        self.assertIn("high", output.getvalue())

    def test_commands_includes_custom_risk_chord_description_and_disabled_state(self):
        import tempfile
        from pathlib import Path

        from wayland_voice_control.commands import CustomShortcut
        from wayland_voice_control.storage import SettingsStore

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "private" / "settings.db"
            store = SettingsStore(path)
            store.add_custom_shortcut(
                CustomShortcut("save", "save file", "Ctrl+S", "Save document")
            )
            store.add_custom_shortcut(
                CustomShortcut("find", "find text", "Ctrl+F", enabled=False)
            )
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                try:
                    result = main(["commands", "--settings", str(path)])
                except SystemExit:
                    self.fail("commands must accept a custom configuration path")
            self.assertEqual(result, 0)
            for value in (
                "save file",
                "Ctrl+S",
                "custom",
                "high",
                "Save document",
                "find text",
                "disabled",
            ):
                self.assertIn(value, output.getvalue())

    def test_doctor_json(self):
        output = io.StringIO()
        with (
            patch(
                "wayland_voice_control.__main__.diagnose",
                return_value={"session_type": "wayland"},
            ),
            contextlib.redirect_stdout(output),
        ):
            self.assertEqual(main(["doctor", "--json"]), 0)
        self.assertEqual(json.loads(output.getvalue()), {"session_type": "wayland"})

    def test_default_lazily_launches_native_app(self):
        app = types.ModuleType("wayland_voice_control.app")
        app.main = lambda: 17
        with patch.dict(sys.modules, {"wayland_voice_control.app": app}):
            self.assertEqual(main([]), 17)

    def test_installed_command_entrypoint(self):
        import tomllib
        from pathlib import Path

        project = Path(__file__).resolve().parents[1] / "pyproject.toml"
        metadata = tomllib.loads(project.read_text())
        self.assertEqual(
            metadata["project"].get("scripts", {}).get("wayland-voice-control"),
            "wayland_voice_control.__main__:main",
        )
