"""CLI helpers stay usable without loading GTK; the default launches the app."""

import argparse
import json
from pathlib import Path

from .commands import COMMANDS
from .diagnostics import diagnose
from .storage import SettingsError, SettingsStore, default_settings_path


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Offline, confirmed Wayland voice assistance"
    )
    subparsers = parser.add_subparsers(dest="command")
    doctor = subparsers.add_parser(
        "doctor", help="Read-only local capability diagnostics"
    )
    doctor.add_argument(
        "--json", action="store_true", help="Print machine-readable diagnostics"
    )
    commands = subparsers.add_parser(
        "commands", help="Show exact built-in and custom phrases, chords and risks"
    )
    commands.add_argument(
        "--settings", type=Path, help="Use a specific settings database"
    )
    arguments = parser.parse_args(argv)
    if arguments.command == "commands":
        path = arguments.settings or default_settings_path()
        try:
            custom = (
                SettingsStore(path).load_custom_shortcuts()
                if path.exists() or arguments.settings
                else ()
            )
        except SettingsError as error:
            parser.error(str(error))
        for command in COMMANDS.values():
            print(f"{command.phrase:20} {command.key_chord:12} {command.risk.value}")
        for item in custom:
            print(
                f"{item.phrase:20} {item.key_chord:12} high custom "
                f"{'enabled' if item.enabled else 'disabled'} {item.description}"
            )
        return 0
    if arguments.command == "doctor":
        report = diagnose()
        if arguments.json:
            print(json.dumps(report, indent=2, sort_keys=True))
        else:
            for key, value in report.items():
                print(
                    f"{key}: {json.dumps(value) if isinstance(value, dict) else value}"
                )
        return 0
    from .app import main as app_main

    return app_main()


if __name__ == "__main__":
    raise SystemExit(main())
