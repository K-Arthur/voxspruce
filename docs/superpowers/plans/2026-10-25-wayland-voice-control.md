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

- [x] Write failing tests for portal request subscription-before-call, request tokens/paths, denial/timeout cleanup, actual granted keyboard bit, session Closed revocation, input rejection without grant, press/release cleanup, and shortcut press/release events scoped to the correct session. Use a deterministic fake transport at the D-Bus boundary, not a fake workflow.
- [x] Implement Gio async request transport and RemoteDesktop keyboard-only session. Use official NotifyKeyboardKeysym without EIS. Implement GlobalShortcuts for hold-to-talk, confirm and cancel; expose actual granted triggers. No raw device access or fallback input tools.
- [x] Write failing capture tests for explicit consent, local valid model path, duplicate start, max duration, cancel during startup/capture/recognition, subprocess failure/EOF, in-memory streaming, stop and process cleanup. Implement `pw-record --rate=16000 --channels=1 --format=s16 --raw -` without shell, feed chunks to Vosk, cache only the loaded model, drop stale worker completions. Keep errors free of transcript content.
- [x] Write failing coordinator tests for complete capture→review→confirm→dispatch, local focus countdown versus global confirmation, risky second confirmation, edit invalidation, generation checks, emergency stop/revoke while pending/scheduled, and no replay after partial input failure. Implement clean observable state and injectable scheduler/adapters for UI.
- [x] Add read-only `doctor` CLI with JSON output and honest capability states, `commands` catalogue CLI, optional explicit `portal-test` helper that prints target/focus instructions and never injects before consent. Default `python -m wayland_voice_control` launches GUI via lazy import. Runtime has no network access logic; local models are imported through filesystem paths.
- [x] Run all tests and CLI checks, self-review and commit. Report real hardware validation limits distinctly.

## Task 2b — realtime speech feedback and measured performance

Added for the user's explicit realtime requirement on 25 October 2026.

- [x] Test first: streaming draft updates combine completed segments with current partial results, are bounded and coalesced, never become approved actions, and cannot survive cancel/replacement/finalization. Preserve fixed privacy-safe errors and held capture semantics.
- [x] Add an explicit model preparation operation that loads/caches locally without starting a recorder. Expose loading/ready/error and safe cancellation so first spoken syllables are not lost while a cold model loads. Continue to prohibit capture after release during loading.
- [x] Expose transient draft text and model readiness through coordinator snapshots for the native UI; clear drafts on release/final/error/cancel/stop and prevent stale prepare/partial callbacks from affecting newer work.
- [x] Provide a reproducible local-WAV benchmark using the application's streaming decoding path. Report cold load, audio duration, decode time, realtime factor, chunk latency percentiles, and finalization latency; print no transcript by default and never capture audio or download assets. Run on the public upstream fixture and document measured hardware/model-specific limits.
- [x] Run all tests, Ruff and private Gio protocol verification; commit progressively; specification review then quality review before native UI integration.

## Task 2c — custom voice shortcuts and safe editing

Added for the user's explicit customization request on 25 October 2026.

- [x] Test and implement persisted custom command phrases mapped to a single validated keyboard chord, with description and enabled state. Exact normalized phrase matching; collisions with built-ins or other custom phrases are rejected. Bound field lengths and catalogue size. No shell commands, scripts, typed secrets, chained macros or automatic execution.
- [x] Add an explicit transactional v1→v2 SQLite migration preserving preferences, a settings table plus custom shortcut configuration table, matching JSON Schemas, CRUD validation and corruption/future-version tests. Custom configurations are intentional persistent preferences, never recognition history.
- [x] Snapshot each reviewed command's actual key plan so changes cannot alter already reviewed input. All custom commands require two separate confirmations because their application effects are unknown. Editing, disabling or deleting a shortcut cancels pending/recording/scheduled work before replacing the catalogue; preserve key-release cleanup and isolated practice behavior.
- [x] Make transcript editing safe and usable: starting an edit immediately removes executable approval, including global confirmation; empty/invalid intermediate text can be corrected without recording again. Re-review creates a fresh expiring action identity. Test select-all/delete/retype, cancel, expiry and stale edits without inventing a microphone recording.
- [x] Expose clear controller APIs for the GUI, update CLI catalogue output and all affected architecture/schema/privacy/manual-test docs, run full tests/Ruff/private-Gio verification, commit; specification review then quality review. Specification and code-quality reviews are approved; all listed checks passed.

## Task 3 — accessible native app, distribution and documentation

Files: `src/wayland_voice_control/{app,window,views,ui_model}.py` (split views as appropriate), `src/wayland_voice_control/resources/*`, `tests/test_ui*.py`, `data/*`, `scripts/*`, `.github/workflows/ci.yml`, `README.md`, `LICENSE`, `docs/{architecture,privacy,compatibility,manual-test,development}.md`.

- [x] Write failing GUI/presentation tests for setup readiness, mode separation, hold release/cancel, pending review and invalidation, second confirmation, focus countdown, emergency stop, actual errors, settings save/reset and isolated practice mode. Test real GTK widgets under Xvfb with injected adapters.
- [x] Build native libadwaita Voice, Commands and Setup views, system themes, large semantic controls, wrapping labels, keyboard shortcut hints, transcript editing, live mic status and emergency stop. Make all visible controls functional. Expose model chooser/preparation, explicit mic consent, portal grant/revoke, global shortcut binding, focus delay and optional local read-back. Add custom voice-shortcut creation/editing/deletion, enable toggles, exact phrase/key previews and practice actions. Missing optional dependencies show actionable recovery instead of crashing. Never start recording on launch or open a consent dialog without user action.
- [x] Add a clearly marked interactive practice mode with text/command input and output preview that cannot execute desktop input or open the mic. Add native app icon, desktop entry, local install/run scripts, wheel/sdist package configuration, and CLI help.
- [x] Document install steps for Debian/Ubuntu and Arch, local model setup/link, runtime offline guarantees and memory limits, SQL/JSON schema, state flow, exact command list, consent semantics, focus/Unicode limits, unsupported desktops and GNOME kill test. Include source-linked technical research and the separate Vibe data-availability report. No invented validation or certification claims.
- [x] CI: unittest pure suite, dependencies and Xvfb GTK smoke test, compileall, build wheel/sdist and inspect installed entry point. Run complete checks locally and launch/render actual GTK app for inspection at compact and desktop sizes. Record evidence and remaining manual validation.
- [ ] Specification review, then code-quality review; fix findings with regression tests; final integrated review; commit and deliver files in the user's workspace.

## Acceptance

- [ ] All task reviews approved; tests and build pass freshly.
- [x] App launches offline without Vosk/model and explains setup; practice mode works end to end.
- [x] Audio and actual input adapters are implemented, permission-gated and tested at their protocol boundaries.
- [x] GNOME kill-test status is honest; unperformed hardware/voice/accessibility-user tests remain explicit release gates.
