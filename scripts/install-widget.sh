#!/usr/bin/env bash
# Explicit per-user registration. Never adds an applet, starts Plasma, or autostarts.
set -eu
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
executable="$project_dir/.venv/bin/wayland-voice-control"
if [ ! -x "$executable" ]; then
    echo 'Missing local environment. Run scripts/install-local.sh first.' >&2
    exit 1
fi
if ! command -v kpackagetool6 >/dev/null 2>&1; then
    echo 'Missing kpackagetool6. Install Plasma 6.7 or newer first.' >&2
    exit 1
fi
# D-Bus Exec is an argument vector parsed by D-Bus, not a shell command.
# Python preserves arbitrary absolute checkout names and validates XDG paths.
python3 - "$project_dir" <<'PY'
import os
from pathlib import Path
import subprocess
import sys

project = Path(sys.argv[1])
data_home = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share")
if not data_home.is_absolute():
    data_home = Path.home() / ".local/share"
plugin = "io.github.wayland_voice_control"
source = project / "integrations/plasma" / plugin
installed = data_home / "plasma/plasmoids" / plugin
# Install before writing activation registration, so failed package validation
# leaves no new activation entry behind.
subprocess.run(["kpackagetool6", "--type", "Plasma/Applet",
                "--upgrade" if installed.exists() else "--install", str(source)], check=True, env=dict(os.environ, XDG_DATA_HOME=str(data_home)))
executable = str(project / ".venv/bin/wayland-voice-control")
if "\n" in executable or "\r" in executable:
    raise SystemExit("Checkout paths containing newlines cannot be registered.")
escaped = executable.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$").replace("`", "\\`")
# Service files decode escapes before the activation argument parser.
escaped = escaped.replace("\\", "\\\\")
template = (project / "data" / (plugin + ".service")).read_text()
service = template.replace("Exec=wayland-voice-control", 'Exec="' + escaped + '"')
services = data_home / "dbus-1/services"
services.mkdir(parents=True, exist_ok=True)
target = services / (plugin + ".service")
target.write_text(service)
print("Installed widget and D-Bus activation:", target)
print("Add Voxspruce using Plasma's widget chooser when wanted.")
PY
