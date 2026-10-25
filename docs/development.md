# Development and distribution

Use Python 3.11+ with system GTK4/libadwaita/PyGObject. See README for Debian/Ubuntu
and Arch dependencies. A virtual environment must use `--system-site-packages`
so it sees the distribution's `gi` package. Pure backend/CLI checks do not import
GTK and work without a display or the optional Vosk dependency.

```sh
python3 -m venv --system-site-packages .venv
.venv/bin/python -m pip install -e . build ruff 'setuptools>=77' wheel
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v
.venv/bin/ruff check src tests scripts
.venv/bin/python -m compileall -q src tests scripts
```

Native tests need GTK, Xvfb, D-Bus and libXtst (`libxtst6` on Debian/Ubuntu).
They create temporary private preferences and inject fake audio/input boundaries.
Actual GTK widgets, keyboard routing and XTest events are used on the private
Xvfb display; no host input or microphone is touched. `GTK_A11Y=test` permits
assertions about programmatic names without requiring an accessibility bus.

```sh
WVC_GTK_TESTS=1 GDK_BACKEND=x11 GSK_RENDERER=cairo GTK_A11Y=test GIO_USE_VFS=local \
  dbus-run-session -- xvfb-run -a .venv/bin/python -m unittest tests.test_ui_gtk -v
PYTHONPATH=src .venv/bin/python scripts/check-portal-protocol.py
```

GTK tests are opt-in during pure discovery and run explicitly in CI. Optional
installed-Vosk/native diagnostic cases skip if their engine/fixture is absent;
see validation.md for the host run. The protocol check runs the real Gio wire
against a fake service inside its own private D-Bus session. Starting GTK can
activate desktop portal services on that isolated bus; the Practice factory
never creates a live input/capture adapter or requests permission.

Build and inspect distributions:

```sh
.venv/bin/python -m build --no-isolation
python3 -m venv --system-site-packages /tmp/wvc-install
/tmp/wvc-install/bin/python -m pip install --no-deps dist/*.whl
cd /tmp
/tmp/wvc-install/bin/wayland-voice-control --help
/tmp/wvc-install/bin/wayland-voice-control commands
/tmp/wvc-install/bin/wayland-voice-control doctor --json
```

Setuptools 77+ is the declared build dependency. A wheel includes native UI
modules, both SQLite resources, its source-run app icon, desktop entry, hicolor
SVG and both JSON schemas. The sdist additionally includes source, tests, docs,
scripts and Linux CI. There are no mandatory PyPI runtime dependencies: desktop
libraries come from the distribution; `[speech]` adds Vosk. The application-menu
installer writes a launcher tied to this checkout's venv and a matching hicolor
icon under the user's data directory. It does not require root.

`.github/workflows/ci.yml` runs on Ubuntu 24.04 with native dependencies, pure
tests, Ruff, compileall, Xvfb GTK/XTest tests, private Gio protocol integration,
wheel/sdist build and installed CLI/resource inspection. CI configuration does
not claim a remote Actions run occurred until one is recorded.

The default launcher starts a fresh isolated Practice controller. Live mode
constructs `RequestTransport(GioWire())`, `RemoteDesktop`, `GlobalShortcuts` and
`AudioCapture` only after explicit selection; consent/recording remain separate
actions. UI observers and all public controller calls stay on the GTK thread.

Before changing approval, editing, capture or cancellation behavior, add a failing
behavioral regression and observe RED, then implement and run GREEN. Recheck
native display attachment as well as widget signals: an unattached Gtk.Stack can
pass signal-only tests. Inspect real rendered windows at compact/desktop widths,
large fonts and light/dark themes. Real GNOME grants/input/microphone/Orca/user
usability still require the separate manual checklist.
