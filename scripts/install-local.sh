#!/usr/bin/env bash
# Explicit local install; installs Python speech dependencies using pip.
set -eu
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
python3 -m venv --system-site-packages "$project_dir/.venv"
"$project_dir/.venv/bin/python" -m pip install -e "$project_dir[speech]"
"$project_dir/.venv/bin/python" - "$project_dir" <<'PY'
import os
import shutil
import sys
from pathlib import Path

project = Path(sys.argv[1])
data_home = Path(os.environ.get('XDG_DATA_HOME') or Path.home() / '.local/share')
if not data_home.is_absolute():
    data_home = Path.home() / '.local/share'
applications = data_home / 'applications'
icons = data_home / 'icons/hicolor/scalable/apps'
applications.mkdir(parents=True, exist_ok=True)
icons.mkdir(parents=True, exist_ok=True)
executable = str(project / '.venv/bin/wayland-voice-control')
escaped = executable.replace('\\', '\\\\').replace('"', '\\"').replace('`', '\\`').replace('$', '\\$').replace('%', '%%')
desktop = (project / 'data/io.github.wayland_voice_control.desktop').read_text()
desktop = desktop.replace('Exec=wayland-voice-control', 'Exec="' + escaped + '"')
(applications / 'io.github.wayland_voice_control.desktop').write_text(desktop)
shutil.copyfile(project / 'data/io.github.wayland_voice_control.svg', icons / 'io.github.wayland_voice_control.svg')
print('Installed desktop launcher:', applications / 'io.github.wayland_voice_control.desktop')
print('Start with scripts/run-local.sh. Models are configured separately; nothing records on launch.')
PY
