"""Widget installation stays explicitly per-user and never executes through a shell."""

import configparser
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = "io.github.wayland_voice_control"


class WidgetPackageTests(unittest.TestCase):
    def test_archive_is_deterministic_with_metadata_at_root(self):
        self.assertTrue(
            (ROOT / "scripts/build-widget.py").is_file(), "widget builder is missing"
        )
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "widget.zip"
            command = [
                sys.executable,
                str(ROOT / "scripts/build-widget.py"),
                "--output",
                str(output),
            ]
            subprocess.run(command, check=True, capture_output=True)
            first = output.read_bytes()
            subprocess.run(command, check=True, capture_output=True)
            self.assertEqual(first, output.read_bytes())
            with zipfile.ZipFile(output) as archive:
                metadata = json.loads(archive.read("metadata.json"))
                self.assertEqual(metadata["KPackageStructure"], "Plasma/Applet")
                self.assertEqual(metadata["X-Plasma-API-Minimum-Version"], "6.7")
                self.assertIn("contents/ui/ControlBridge.qml", archive.namelist())
                self.assertEqual(archive.testzip(), None)

    def install(self, *, update=False, relative_xdg=False, missing_venv=False):
        self.assertTrue(
            (ROOT / "scripts/install-widget.sh").is_file(),
            "widget installer is missing",
        )
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        base = Path(temp.name)
        project = base / 'checkout space $dollar `tick` "quote" \\ slash'
        (project / "scripts").mkdir(parents=True)
        shutil.copy(ROOT / "scripts/install-widget.sh", project / "scripts")
        shutil.copytree(ROOT / "integrations", project / "integrations")
        shutil.copytree(ROOT / "data", project / "data")
        executable = project / ".venv/bin/wayland-voice-control"
        executable.parent.mkdir(parents=True)
        if not missing_venv:
            executable.write_text("#!/bin/sh\nexit 0\n")
            executable.chmod(0o755)
        tools = base / "tools"
        tools.mkdir()
        log = base / "calls.jsonl"
        tool = tools / "kpackagetool6"
        tool.write_text(
            "#!"
            + sys.executable
            + '\nimport json, os, sys\nwith open(os.environ["WIDGET_TEST_LOG"], "a") as f: f.write(json.dumps(sys.argv[1:]) + "\\n")\n'
        )
        tool.chmod(0o755)
        data_home = base / "xdg data"
        home = base / "home"
        if update:
            (data_home / "plasma/plasmoids" / PLUGIN).mkdir(parents=True)
        env = dict(
            os.environ,
            HOME=str(home),
            XDG_DATA_HOME="relative" if relative_xdg else str(data_home),
            PATH=str(tools) + os.pathsep + os.environ["PATH"],
            WIDGET_TEST_LOG=str(log),
        )
        result = subprocess.run(
            ["bash", str(project / "scripts/install-widget.sh")],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        return (
            result,
            log,
            executable,
            home / ".local/share" if relative_xdg else data_home,
        )

    def test_installer_quotes_absolute_activation_path_and_installs_only(self):
        result, log, executable, data_home = self.install()
        self.assertEqual(result.returncode, 0, result.stderr)
        parser = configparser.ConfigParser(interpolation=None)
        parser.read(data_home / "dbus-1/services" / (PLUGIN + ".service"))
        command = parser["D-BUS Service"]["Exec"]
        # D-Bus activation uses GLib's shell argument parser; no shell is run.
        try:
            from gi.repository import GLib
        except ImportError:
            import shlex

            argv = shlex.split(command.replace("\\\\", "\\"))
        else:
            keyfile = GLib.KeyFile()
            keyfile.load_from_file(
                str(data_home / "dbus-1/services" / (PLUGIN + ".service")),
                GLib.KeyFileFlags.NONE,
            )
            argv = GLib.shell_parse_argv(keyfile.get_string("D-BUS Service", "Exec"))[1]
        self.assertEqual(list(argv), [str(executable), "gui", "--background"])
        calls = [json.loads(line) for line in log.read_text().splitlines()]
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][:3], ["--type", "Plasma/Applet", "--install"])
        self.assertFalse((data_home / "autostart").exists())

    def test_installer_update_and_relative_xdg_fallback(self):
        result, log, _, _ = self.install(update=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--upgrade", json.loads(log.read_text()))
        result, _, _, data_home = self.install(relative_xdg=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(
            (data_home / "dbus-1/services" / (PLUGIN + ".service")).exists()
        )

    def test_missing_venv_is_actionable_and_does_not_register(self):
        result, log, _, data_home = self.install(missing_venv=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("install-local.sh", result.stderr)
        self.assertFalse(log.exists())
        self.assertFalse((data_home / "dbus-1/services").exists())

    def test_distribution_declares_widget_and_activation_resources(self):
        import tomllib

        project = tomllib.loads((ROOT / "pyproject.toml").read_text())
        files = project["tool"]["setuptools"]["data-files"]
        self.assertIn("share/dbus-1/services", files)
        self.assertIn(
            "data/io.github.wayland_voice_control.service",
            files["share/dbus-1/services"],
        )
        self.assertIn(
            "integrations/plasma/" + PLUGIN + "/metadata.json",
            files["share/wayland-voice-control/plasma/" + PLUGIN],
        )
        manifest = (ROOT / "MANIFEST.in").read_text()
        self.assertIn("recursive-include integrations *.json *.qml", manifest)
        self.assertIn("*.service", manifest)
