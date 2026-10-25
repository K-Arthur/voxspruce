# Wayland Voice Control — implementation design

Date: 2026-10-25. Source: user-provided “Wayland Voice Control, Narrow and Offline, 28/35”.

## Product boundary

A free MIT-licensed native Linux community tool for push-to-talk dictation and a small set of explicitly confirmed keyboard commands. GNOME Wayland is the first validation target. Other desktops are experimental until a recorded compatibility run succeeds. This is not certified assistive technology. No always-listening mode, cloud fallback, arbitrary shell commands, account system, billing, analytics upload, or background microphone capture.

## Architecture decision

Use Python 3.11+, GTK4 and libadwaita, Gio D-Bus, PipeWire `pw-record`, Vosk with a locally installed small English model, SQLite and stdlib unittest. The user selected Python + GTK4. A Rust/TypeScript shell adds a web/native bridge without resolving the core input risk; a command-line-only spike is useful for diagnostics but insufficient for accessible onboarding. Native GTK provides semantic controls and system typography with a smaller runtime boundary.

Separate pure domain policy, persistence, operating-system adapters, application coordination, and GTK views. Hardware and D-Bus adapters are injectable so permission revocation, cancellation and timeouts can be tested without controlling a user's desktop.

## End-to-end workflow

1. Launch with the microphone off. Show setup checklist and actual model, desktop, PipeWire and portal readiness.
2. Choose an extracted local Vosk model directory. Never auto-download or upload anything. Explain that the English command grammar requires an English recognition model.
3. Explicitly enable microphone use in the app. Audio capture starts only during a held button/shortcut, stops on release/cancellation, and has a hard duration cap.
4. Explicitly request keyboard control through RemoteDesktop.CreateSession → SelectDevices(KEYBOARD only) → Start. Check the actual granted-device mask. No input before success. No persistence tokens, screen sharing, uinput, xdotool, ydotool, root or compositor extensions.
5. Optionally bind push-to-talk, confirm and cancel through GlobalShortcuts with the desktop's user-consent dialog. Activated/Deactivated implement hold-to-talk. No raw keyboard monitoring. Local controls work if global shortcuts are unavailable.
6. Choose Dictation or Commands explicitly. Dictation text never doubles as a command. Hold to speak, release to finish. Audio streams from pw-record stdout into Vosk in memory; no audio file is created. UI displays recording/processing/review/error states and a transient streaming draft. Drafts are provisional, never executable, bounded in length, and coalesced to avoid UI callback backlogs. Explicit local model preparation keeps cold loading separate from a held recording. A local-WAV benchmark measures decoder throughput and finalization latency; realtime performance depends on hardware/model and does not bypass review.
7. Show the full recognized text/action for review. Optional local spoken read-back may use `espeak-ng --stdin` when available (text is passed through a pipe, not process arguments); never make network speech calls. Starting a dictation edit removes the executable action immediately, including global confirmation. Empty or invalid intermediate edits remain correctable without recording again; explicit re-review validates the text and creates a fresh pending action with no prior confirmation. Reject control characters and line breaks from injected dictation to prevent Enter/Tab from submitting forms.
8. Confirm a single immutable, expiring action. For local confirmation, show an explicit cancellable focus countdown so the user can select the destination; with a global confirm shortcut the user can remain in the target app. No automatic sending/submitting. The narrow command catalogue contains next field, previous field, copy, paste, undo, select all, and explicitly risky press Enter, close window, delete selection. All require confirmation; risky commands require a separate second confirmation.
9. Execute only the confirmed action through the granted portal session, at most once. Reject stale IDs, expired actions, concurrent recordings, permission revocation, and pending work after stop/disconnect. Release modifiers even when input fails. A failure may have partially typed text: report it and never automatically retry.
10. Return to microphone-off idle. Activity is transient metadata, never a transcript log. Emergency stop cancels capture, pending and scheduled actions and closes keyboard permission. App exit cleans up all processes and sessions.

## Data and schema

Persist only a versioned preferences row: schema version, model path, explicit microphone consent, confirmation TTL, focus delay, capture duration limit, and theme. No audio, transcript, command payload, clipboard, portal token or diagnostic content is stored. Settings are type/range validated, atomically updated, and can be reset. SQLite migrations are versioned; unknown future schemas fail without altering data. Expose the SQL schema and a JSON Schema for settings interchange/documentation. The runtime engine keeps immutable action IDs, kind, payload, risk, created/expiry times and state in memory only.

## Input and focus limitations

The portal can inject keyboard input but cannot prove the semantic identity of a focused text field. The user must review the action and focus its destination. Never claim password-field protection, focus attestation, or a guarantee against an application interpreting a key unexpectedly. Unicode keysym delivery depends on compositor/layout support and must be measured in the GNOME kill test. Any unsupported portal or failed consent is a visible blocked state, not a trigger for a lower-permission fallback. D-Bus NotifyKeyboardKeysym is an officially documented route; do not mix it with an EIS connection.

## UI and accessibility

Native libadwaita window with Voice, Commands, and Setup views. A calm deep-blue primary accent, neutral surfaces, system sans typography, clear status text, 8px spacing, readable line length, and native symbolic icons. Prominent hold-to-talk control, microphone-off state, transcript editor and review card, persistent emergency stop, and progressive setup guidance. Visible labels, native keyboard navigation/focus, screen-reader semantics, no color-only status, large controls, wrapping text and system dark/light themes. No decorative motion. Minimum practical desktop width 560px; narrower windows scroll instead of clipping. A separate interactive practice mode operates only in a local preview and clearly labels simulated input; it never opens microphone or portal permissions.

## Verification and release boundary

TDD for parser, workflow, persistence, portal protocol, capture lifecycle, coordinator and GUI workflows. Linux CI runs unit tests, GTK smoke tests under Xvfb, packaging, and CLI diagnostics. Manual GNOME kill test must record desktop and portal versions, granted/denied/revoked sessions, focused-target test text, Unicode/layout behavior, key cleanup, cancellation, latency, and offline speech accuracy with accents. Current machine: CachyOS/KDE Wayland, GTK 4.24.1; portal introspection succeeds. This does not constitute GNOME input or speech validation. Do not claim production readiness until the matrix is populated by real testing.
