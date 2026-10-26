# Scope and release readiness

The narrow offline implementation and optional desktop widget are built. This is
an experimental community tool. Passing software checks does not establish
reliable physical speech input, compositor insertion or assistive usability.

| Requirement | Implementation and evidence | Remaining release evidence |
| --- | --- | --- |
| Native Python/GTK4 app, setup and Practice | Native Voice/Commands/Setup, safe defaults, local installer, wheel/sdist, CLI diagnostics; native and installed-package checks | Complete first-run tasks on the supported desktop/distribution matrix |
| Offline speech and reasonable realtime feedback | Local Vosk, prepared model, bounded PipeWire capture/drafts, cancellation and replay benchmark; latest host paced RTF 0.216, max replay lag 435 ms | Physical microphone onset/finalization latency, device lifecycle and accuracy across claimed accents/languages/devices |
| Reviewed dictation and exact commands | Literal dictation, validated command chords, expiring single-use review, separate risky approval, countdown, stop/revoke and no retry; domain/controller/protocol regressions | GNOME permission/input kill test, exact disposable-field output, Unicode/layouts and actual key release |
| User voice shortcuts | Persisted validated custom phrases, one chord, descriptions/enabled state, Practice, editing and mandatory second approval; storage/controller/native/AT-SPI tests | Intended-user discovery, correction effort and task usefulness |
| Safe initialization and local privacy | Practice creates no live adapters; explicit consent/grants/model setup; private configuration; no audio/transcript history or runtime network feature | Offline real-session observation and permission-denial/revocation matrix |
| Competing voice apps and desktop shortcut changes | Shared-capture explanation, identifiable stream, actual granted bindings, changed-binding updates; portal loss/replacement cancels work without automatic reconnect/replay | Real simultaneous apps, desktop conflict chooser and other app streams remaining unaffected |
| Available with the main window closed | Explicit session residency, Show controls/global capture, default-instance activation and optional native Plasma widget; actual isolated GTK/QML D-Bus protocol, package and visual checks | Actual GNOME/Plasma focus/grants plus widget lifecycle on each claimed desktop |
| Accessibility for disabled people | Native semantic controls, hold or separate start/finish, explicit local read-back, keyboard tests, selected real AT-SPI Practice actions, compact/enlarged visual checks | Orca speech/braille, high contrast, switch access and consented tasks with intended users; no TalkBack parity claim |
| Public project and reproducible distribution | MIT, progressive public commits, CI, schemas, workflow/security/setup/test documentation, Python and widget artifacts | Captioned real-session demo showing errors/recovery; privacy-preserving participant feedback |

Use [manual-test.md](manual-test.md) to record actual desktop outcomes and
[accessibility.md](accessibility.md) for the intended-user matrix.
[validation.md](validation.md) records software evidence and its limits.
Opening/closing test windows is not confirmation of inserted text. The delayed
report of window activity leaves that input check open. No further spoken phrase
is required to reproduce the automated checks.
