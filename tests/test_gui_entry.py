import contextlib
import io
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from wayland_voice_control.__main__ import main


class GuiEntryTests(unittest.TestCase):
    def test_named_gui_command_accepts_local_settings_path(self):
        received = []
        app = types.ModuleType("wayland_voice_control.app")
        app.main = lambda **kwargs: received.append(kwargs) or 0
        with (
            patch.dict(sys.modules, {"wayland_voice_control.app": app}),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            try:
                result = main(["gui", "--settings", "/tmp/private/settings.db"])
            except SystemExit:
                result = -1
        self.assertEqual(result, 0)
        self.assertEqual(
            received, [{"settings_path": Path("/tmp/private/settings.db")}]
        )

    def test_help_explains_safe_gui_start(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), self.assertRaises(SystemExit):
            main(["--help"])
        self.assertIn("Practice", output.getvalue())


if __name__ == "__main__":
    unittest.main()
