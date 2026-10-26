# Background controls and KDE widget implementation plan

> **For agentic workers:** Use subagent-driven-development task by task, with spec and quality review before proceeding. The user has approved implementation of both scopes.

**Goal:** Make voice control reachable with its window closed and provide a KDE panel/desktop widget without weakening consent or confirmation.

**Architecture:** Retain the GTK/controller as sole owner of the live adapters; expose a small, versioned session-bus control interface. A Plasma QML package reads sanitized status and invokes only fixed lifecycle/capture actions.

**Tech Stack:** Python, GTK4/libadwaita, Gio D-Bus, Plasma 6.7 QML, unittest/QtTest.

## Task 1: Resident app and narrow IPC

Files: `app.py`, a new focused `desktop_control.py`, `__main__.py`, targeted additions to `window.py`, `controller.py`/`portal.py` for Show controls if needed; `tests/test_desktop_control.py`, `tests/test_gui_entry.py`, native integration tests.

- [x] Add failing tests for sanitized status (including malicious transcript/error strings), fixed method dispatch and capture gating.
- [x] Run targeted unittest tests; confirm missing behavior fails, then implement the narrow adapter. A status mapping must never serialize `snapshot.status`, `error`, `pending`, or `draft_text`.
- [x] Add failing tests for CLI `gui --background`, explicit custom-settings instance separation, keeping a hidden app alive, closing cancels capture/countdowns, normal activation reuses a hidden window, explicit quit shuts down, and cold background launch remains Practice.
- [x] Implement a testable application factory, hold/release lifecycle, runtime opt-in background control, Quit and the Controls1 export. Keep lazy imports so headless CLI works. Register Show controls with the global shortcut portal.
- [x] Add native tests for D-Bus calls/signals and controller replacement; use a private bus/display and fake adapters. Exercise GetStatus/Show/Start/Finish/Cancel/Stop/Quit, unavailable/preparation gates and final-review visibility.
- [x] Run pure and native suites plus Ruff; inspect diff, commit. Obtain spec review, fix findings, then quality review and fix findings.

## Task 2: Plasma widget and installation

Files: new `integrations/plasma/io.github.wayland_voice_control/` metadata and QML, QML tests, `scripts/install-widget.sh`, `scripts/build-widget.py`, service template, `pyproject.toml`, `MANIFEST.in`, packaging tests.

- [x] Write and run failing QtTest cases for recording readiness, Start/Finish behavior, cancel/stop, service loss, in-flight clicks, error feedback and accessible controls using an injected fake bridge.
- [x] Implement native themed, wrapping, scrollable controls and compact representation. Use only direct D-Bus calls through `org.kde.plasma.workspace.dbus`; expose no executable-command configuration.
- [x] Test real bridge against a private D-Bus service including activation failure, owner loss/restart, status change and error recovery. Do not invoke arbitrary shell commands or host microphone/input.
- [x] Add deterministic ZIP builder and explicit per-user installer for the service and plasmoid. Installer uses quoted absolute venv path, validates it and never changes panel configuration/autostart. Cover distribution resources and archive contents with tests.
- [x] Load the package with Plasma tooling; run QtTest, take real screenshots and inspect compact/expanded, light/dark, narrow/enlarged text. Commit after review of outputs. Obtain spec then quality review.

## Task 3: Documentation, integration and delivery

Files: README; architecture, adapter-api, privacy, security, accessibility, compatibility, development, manual-test, validation docs; CI native tests; plan checklist.

- [x] Document launch, runtime background setting, widget install/update/remove, explicit cold-start setup, no wake word, safety/trust boundaries, capabilities and desktop/version limits.
- [x] Add the private native IPC tests to CI; document local Qt/Plasma tests separately where Ubuntu lacks the required Plasma module. Build wheel/sdist and widget artifact; inspect installed resource paths and entry points from a clean temporary environment.
- [x] Run full pure and GTK suites, private portal and widget protocol checks, Qt tests, Ruff, compileall, package build/installed checks. Record counts, platform/tool versions and actual visual evidence; mark any real-session manual gaps honestly.
- [x] Obtain final spec then quality review; resolve findings with regressions and rerun affected checks.
- [x] Commit docs/integration, merge the completed feature into `main` as explicitly requested, push all progressive commits and check GitHub Actions on the resulting `main` commit. Confirm clean workspace and remote commit.
