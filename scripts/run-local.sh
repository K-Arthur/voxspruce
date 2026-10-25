#!/usr/bin/env bash
set -eu
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
if [ ! -x "$project_dir/.venv/bin/python" ]; then
  printf '%s\n' 'Run scripts/install-local.sh first; see README.md for desktop dependencies.' >&2
  exit 1
fi
exec "$project_dir/.venv/bin/python" -m wayland_voice_control "$@"
