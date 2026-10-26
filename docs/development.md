# Development and distribution

Use Python 3.11+ with system GTK4/libadwaita/PyGObject. See README for Debian/Ubuntu
and Arch dependencies. A virtual environment must use `--system-site-packages`
so it sees the distribution's `gi` package. Pure backend/CLI checks do not import
GTK and work without a display or the optional Vosk dependency.

```sh
python3 -m venv --system-site-packages .venv
.venv/bin/python -m pip install -e . build ruff 'setuptools>=77' 'packaging>=24.2' wheel
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
PYTHONPATH=src .venv/bin/python scripts/check-accessibility.py
```

The separate `check-accessibility.py` runs real AT-SPI transport and native
Practice actions, including edit/re-review, simulated dictation, custom shortcut
creation/two-stage approval/cancellation, Setup names/default consent and Quit.
It needs the distribution AT-SPI registry and GI typelib (`at-spi2-core` and
`gir1.2-atspi-2.0` on Ubuntu). It creates an activation-free private D-Bus session,
starts its own registry, points GTK/libatspi at that bus and uses Xvfb plus private
XDG/settings directories. A 60-second process-group limit bounds failures. It
prints no synthetic transcript, uses no host accessibility tree, and performs no
physical keyboard/microphone or Orca test. CI runs it independently of
`GTK_A11Y=test`. It compares stable AT-SPI role enum IDs: GTK 4.14
[returns ARIA-style role names](https://github.com/GNOME/gtk/blob/4.14.5/gtk/a11y/gtkatspicontext.c)
while newer GTK returns different strings for some roles. Names and required
semantic roles are still asserted. Named section groups accept GROUPING or
PANEL because Ubuntu Noble's
[GTK compatibility patch](https://archive.ubuntu.com/ubuntu/pool/main/g/gtk4/gtk4_4.14.5+ds-0ubuntu0.10.debian.tar.xz)
intentionally maps GTK GROUP to PANEL for its bundled older Orca. The exact name
and heading remain required, and native GTK tests require GROUP itself. Other
roles remain exact; the check does not accept arbitrary roles. Text reads use
`GetText(0, CharacterCount)` because GTK 4.14 clamps a negative end offset to
zero for GtkEditable. Status content is read through the Text interface: that
GTK version deliberately prohibits an accessible name for the STATUS role.

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
SVG, both JSON schemas, the activation service and Plasma metadata/QML. The
sdist additionally includes source, Python/QML tests, integration sources, docs,
scripts and Linux CI. There are no mandatory PyPI runtime dependencies: desktop
libraries come from the distribution; `[speech]` adds Vosk. The application-menu
installer writes a launcher tied to this checkout's venv and a matching hicolor
icon under the user's data directory. It does not require root.

`.github/workflows/ci.yml` runs on Ubuntu 24.04 with native dependencies, pure
tests, Ruff, compileall, Xvfb GTK/XTest tests, private Gio protocol integration,
wheel/sdist build and installed CLI/resource inspection. The first successful
public run passed all checks for commit `dcc7eb5` ([GitHub Actions](https://github.com/K-Arthur/wayland-voice-control/actions/runs/40237283310)).

A fresh process starts an isolated Practice controller. A later launch presents
the existing resident controller without reconnecting or replaying work. Live mode
constructs `RequestTransport(GioWire())`, `RemoteDesktop`, `GlobalShortcuts` and
`AudioCapture` only after explicit selection; consent/recording remain separate
actions. UI observers and all public controller calls stay on the GTK thread.

Before changing approval, editing, capture or cancellation behavior, add a failing
behavioral regression and observe RED, then implement and run GREEN. Recheck
native display attachment as well as widget signals: an unattached Gtk.Stack can
pass signal-only tests. Inspect real rendered windows at compact/desktop widths,
large fonts and light/dark themes. Real GNOME grants/input/microphone/Orca/user
usability still require the separate manual checklist.

## Resident application and Plasma integration

Native CI now includes `tests.test_app` alongside `tests.test_ui_gtk`. Its separate
Gio client connection exercises the actual Controls1 wire, and subprocess cases
exercise cold background launch, second launch and Quit response/exit ordering.
All use temporary private preferences and fake live adapters.

On the Plasma 6.7+ development host, the widget's QML tests use Qt Quick Test and
the installed workspace D-Bus QML module:

```sh
QT_NO_XDG_DESKTOP_PORTAL=1 QT_QPA_PLATFORMTHEME=generic \
  QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software \
  QT_QUICK_CONTROLS_STYLE=org.kde.desktop \
  dbus-run-session -- /usr/lib/qt6/bin/qmltestrunner -input tests/qml
.venv/bin/python scripts/check-widget-protocol.py
.venv/bin/python scripts/build-widget.py
```

The Ubuntu 24.04 CI image does not supply that Plasma version. Use the Qt 6
runner path provided by the distribution; an unversioned runner may select Qt 5.
QML/Plasma runtime verification is recorded separately on the compatible host;
Python packaging checks, widget archive build and resident/native IPC tests still
run in CI. The uploaded distribution artifact includes the `.plasmoid` archive.
Use a private D-Bus session
and temporary XDG data/config paths for widget protocol/package tests. Do not
replace the running shell or change the user's panel for automated verification.
Inspect rendered normal/narrow widgets, light/dark themes and enlarged text;
real Wayland focus/portal/Orca/user testing remains a separate manual matrix.
