# Wayland Voice Control Implementation Plan

> **For agentic workers:** Use subagent-driven-development with fresh implementers and specification review followed by code-quality review. Use test-driven-development for every behavior change.

**Goal:** Build a runnable native offline voice-control application with explicit permissions, reviewed input, documented schemas, diagnostics and Linux CI.

**Architecture:** Pure Python domain and storage modules isolate policy from Gio portals, PipeWire and Vosk. A coordinator joins adapters to a native GTK4/libadwaita UI. No network calls are made by runtime code.

**Tech stack:** Python 3.11+, GTK4/libadwaita/PyGObject, Gio/GLib, Vosk, PipeWire, SQLite, unittest, setuptools.

## Task 1 — domain, safety policy and schema

Files: `pyproject.toml`, `src/wayland_voice_control/{__init__,domain,commands,storage}.py`, `src/wayland_voice_control/schema.sql`, `schemas/settings.schema.json`, `tests/test_{domain,commands,storage}.py`.

- [x] Write failing unittest cases for literal dictation versus explicit command mode, exact normalized allowlist matching, rejected unknown commands, control characters, action expiry, stale IDs, edit invalidation, second confirmation for risky commands, single execution, revoke/stop cancellation, and invalid state transitions. Example contract: `match_command('  NEXT field ')` resolves `next_field`; `match_command('next field then send')` raises a validation error. Never fuzzy match.
- [x] Run `python3 -m unittest discover -s tests -v`; observe intended assertions fail before adding implementation. Establish minimal imports/stubs only if needed to make failures behavioral.
- [x] Implement enums/dataclasses, immutable pending actions with IDs/expiry, explicit workflow transitions, and immutable catalogue. Bind executable plans to reviewed actions. Reject malformed data at public boundaries; no Enter, Tab or control characters inside dictated text. Cap transcript length. No execution side effect in this layer.
- [x] Write failing tests using temporary SQLite databases for defaults, persistence round-trip, invalid range/type rejection, reset, migration/version handling and absence of content columns. Implement atomic validated settings, restrictive file permissions and packaged schema SQL. Publish matching JSON Schema.
- [x] Run complete tests; self-review; commit. Report APIs and observed RED/GREEN evidence.

## Task 2 — desktop, audio and application workflow

Files: `src/wayland_voice_control/{portal,audio,controller,diagnostics,__main__}.py`, additional focused adapter modules if needed; `tests/test_{portal,audio,controller,diagnostics,cli}.py`.

- [ ] Write failing tests for portal request subscription-before-call, request tokens/paths, denial/timeout cleanup, actual granted keyboard bit, session Closed revocation, input rejection without grant, press/release cleanup, and shortcut press/release events scoped to the correct session. Use a deterministic fake transport at the D-Bus boundary, not a fake workflow.
- [ ] Implement Gio async request transport and RemoteDesktop keyboard-only session. Use official NotifyKeyboardKeysym without EIS. Implement GlobalShortcuts for hold-to-talk, confirm and cancel; expose actual granted triggers. No raw device access or fallback input tools.
- [ ] Write failing capture tests for explicit consent, local valid model path, duplicate start, max duration, cancel during startup/capture/recognition, subprocess failure/EOF, in-memory streaming, stop and process cleanup. Implement `pw-record --rate=16000 --channels=1 --format=s16 --raw -` without shell, feed chunks to Vosk, cache only the loaded model, drop stale worker completions. Keep errors free of transcript content.
- [ ] Write failing coordinator tests for complete capture→review→confirm→dispatch, local focus countdown versus global confirmation, risky second confirmation, edit invalidation, generation checks, emergency stop/revoke while pending/scheduled, and no replay after partial input failure. Implement clean observable state and injectable scheduler/adapters for UI.
- [ ] Add read-only `doctor` CLI with JSON output and honest capability states, `commands` catalogue CLI, optional explicit `portal-test` helper that prints target/focus instructions and never injects before consent. Default `python -m wayland_voice_control` launches GUI via lazy import. Runtime has no network access logic; local models are imported through filesystem paths.
- [ ] Run all tests and CLI checks, self-review and commit. Report real hardware validation limits distinctly.

## Task 3 — accessible native app, distribution and documentation

Files: `src/wayland_voice_control/{app,window,views,ui_model}.py` (split views as appropriate), `src/wayland_voice_control/resources/*`, `tests/test_ui*.py`, `data/*`, `scripts/*`, `.github/workflows/ci.yml`, `README.md`, `LICENSE`, `docs/{architecture,privacy,compatibility,manual-test,development}.md`.

- [ ] Write failing GUI/presentation tests for setup readiness, mode separation, hold release/cancel, pending review and invalidation, second confirmation, focus countdown, emergency stop, actual errors, settings save/reset and isolated practice mode. Test real GTK widgets under Xvfb with injected adapters.
- [ ] Build native libadwaita Voice, Commands and Setup views, system themes, large semantic controls, wrapping labels, keyboard shortcut hints, transcript editing, live mic status and emergency stop. Make all visible controls functional. Expose model chooser, explicit mic consent, portal grant/revoke, global shortcut binding, focus delay and optional local read-back. Missing optional dependencies show actionable recovery instead of crashing. Never start recording on launch or open a consent dialog without user action.
- [ ] Add a clearly marked interactive practice mode with text/command input and output preview that cannot execute desktop input or open the mic. Add native app icon, desktop entry, local install/run scripts, wheel/sdist package configuration, and CLI help.
- [ ] Document install steps for Debian/Ubuntu and Arch, local model setup/link, runtime offline guarantees and memory limits, SQL/JSON schema, state flow, exact command list, consent semantics, focus/Unicode limits, unsupported desktops and GNOME kill test. Include source-linked technical research and the separate Vibe data-availability report. No invented validation or certification claims.
- [ ] CI: unittest pure suite, dependencies and Xvfb GTK smoke test, compileall, build wheel/sdist and inspect installed entry point. Run complete checks locally and launch/render actual GTK app for inspection at compact and desktop sizes. Record evidence and remaining manual validation.
- [ ] Specification review, then code-quality review; fix findings with regression tests; final integrated review; commit and deliver files in the user's workspace.

## Acceptance

- [ ] All task reviews approved; tests and build pass freshly.
- [ ] App launches offline without Vosk/model and explains setup; practice mode works end to end.
- [ ] Audio and actual input adapters are implemented, permission-gated and tested at their protocol boundaries.
- [ ] GNOME kill-test status is honest; unperformed hardware/voice/accessibility-user tests remain explicit release gates.
