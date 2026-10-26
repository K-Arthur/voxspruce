# Validation evidence

Recorded 25 October 2026. This document separates automated/software evidence from unperformed desktop and user testing.

## Development environment

- CachyOS Linux, KDE Wayland; Python 3.14.8; GTK 4.24.1; libadwaita 1.10.0.
- Read-only introspection found RemoteDesktop version 2 with keyboard capability and the GlobalShortcuts interface. No real portal grant or input injection is implied.
- Development dependencies were installed in a repository-local virtual environment; no system packages or desktop configuration were changed.

## Core implementation

- Task 1 commit `70a08b0`: 42 unittest cases pass, covering commands, workflow and real temporary SQLite databases.
- Independent specification and code-quality reviewers approved the core with no blocking findings.
- Ruff passes for the core. A built wheel can import the package and initialize settings using its packaged SQL schema.

## Actual local speech engine

- Vosk 0.3.45 successfully loads the official `vosk-model-small-en-us-0.15` model on this host.
- One second of generated PCM silence produces an empty transcript.
- Vosk's public [upstream test WAV](https://github.com/alphacep/vosk-api/blob/master/python/example/test.wav), processed through the application's `StreamingDecoder`, starts with `one zero zero zero one` and ends with `zero one eight zero three`. This checks the decoder and model, not microphone capture, word-error rate, accent coverage or application integration.
- The observed middle sequence included misrecognitions (for example, `nah no to i know`). This is a real limitation of the small model on that sample, not a claim of perfect transcription.
- Downloaded model and public test fixture are development assets in ignored `models/`; no user microphone was recorded for these checks. Runtime code does not download models.

## Real Gio protocol integration

The application's actual Gio transport and portal adapters were exercised against a temporary portal service under `dbus-run-session`, isolated from the user's desktop bus. The check passed for asynchronous requests, responses emitted before method replies, keyboard-only device options, ASCII/Unicode keysym press/release pairs, returned shortcut descriptions, repeat/release filtering, and session revocation. This validates D-Bus signatures and event wiring; it does not prove compositor text insertion or real permission UI behavior.

Task 2 commits `a0b60eb` and `5530ce7` bring the suite to 98 passing tests. Specification review identified and verified a correction that prevents arbitrary recognizer/cleanup exception text from reaching observable errors. The read-only `doctor --json` command confirms local dependencies and portal availability while reporting that no model has yet been selected in saved preferences.

## Release gates still requiring a person and real desktop session

The GNOME input kill test, real portal consent/revocation, focused-app input, global shortcut behavior, physical microphone lifecycle, speech accuracy/latency across accents and devices, and testing with intended voice-input users must be recorded using [manual-test.md](manual-test.md). They cannot be inferred from unit tests, the development host's portal availability or headless GTK rendering.

Task 2 quality review approved commits `0ce794e` and `f427c98`: stale transcript edits preserve unrelated active operations, and pending permission requests have separate cancellation identities. The complete suite now has 108 passing tests; Ruff and the private Gio protocol check pass. Realtime draft feedback and native UI are the next implementation stages.

## Realtime local speech feedback

Task 2b adds the shared bounded streaming decoder (`a7ce83b`) and draft/model
preparation adapters (`389c136`). New tests were observed failing before their
implementations, then passing: replaceable partials vs finalized segments,
malformed/oversized payload privacy, coalesced/throttled queued drafts, real worker
cancellation during model load, no microphone during explicit preparation, stale
queued readiness/errors, and controller drafts that never create pending actions.
Subsequent regression tests caught and fixed readiness stuck in loading, an empty
late draft after failure, and a burst after a stalled dispatcher resumed.

The reproducible [speech benchmark](performance.md) uses the application's actual
streaming decoder on the existing public upstream WAV (8.308 s), without a
microphone, network, audio copies or transcript output. Two unpaced fresh-process
runs measured realtime factors 0.402 and 0.415, model loads 1.981/1.588 s, and maximum
chunk costs 1.245/0.818 s. A paced replay measured factor 0.262 and maximum accumulated
decode lag 0.645 s. Full environment, percentile/finalization measurements and
metric definitions are recorded in performance.md. Average throughput meets the
<0.5 host target, while observed decode bursts limit promptness. No end-to-end
microphone latency, accent accuracy or other-hardware realtime claim follows.

Final Task 2b validation: 131 unittest cases pass using
`PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v`;
`.venv/bin/ruff check src tests scripts` and
`PYTHONPATH=src .venv/bin/python scripts/check-portal-protocol.py` pass.
Benchmark tests verify real shared decoder block boundaries, nearest-rank
percentiles, measured finalization/compute time, paced scheduling lag, WAV format
and duration rejection, truncated PCM and sanitized failures. No physical
microphone or host portal was exercised.

Independent paced benchmark recheck using the committed shared decoder: 8.308 seconds of audio, 1.881 seconds decoding (RTF 0.226), 407 ms maximum replay lag and 39 ms finalization. This confirms the benchmark is reproducible on this host, not a microphone-latency or recognition-accuracy claim. See [performance.md](performance.md) for all recorded runs, including slower bursts.

## Accessibility controls and headless visual check

GTK/Xvfb tests exercise programmatic labels, GTK widget roles, named section
groups, levelled headings, a status role with state announcements that omit
transcript content, and the Live start/stop alternative for people who cannot
sustain a press. A role-isolation regression test guards against assigning the
status role to ordinary labels. The alternative cancels during microphone
startup, finishes with a second activation after recording starts, and cancels if
the app loses focus. An XTest Space press/release test also starts and stops the
control through the real GTK keyboard event route. Both recording controls use
the configured duration cap.
These tests use `GTK_A11Y=test`; they validate GTK's test backend and announcement
API, not AT-SPI transport or Orca output.

The updated Live Voice view was visually checked under Xvfb at 780×820 and
550×820. At the compact width, instructions wrap cleanly, the new start/stop
control remains fully visible, and review content continues below in the
scrollable view. Latest captures and baseline enlarged-text screenshots are in
the ignored `.worktrees/implementation/artifacts/ui/` development directory. The
isolated Xvfb session could not connect to
the user's AT-SPI registry; no Orca executable is installed in this environment.
Actual screen-reader speech/braille, high-contrast behavior, switch access, speech
accessibility with disabled users, and usability with intended users remain open
manual validation items. See [accessibility.md](accessibility.md) for the target
matrix and claim boundary. No broad claim that the app is optimized for disabled
people or conforms to WCAG follows from these tests.


## Native diagnostic regression

Quality review reproduced native Vosk error output containing an invalid local
model path despite `SetLogLevel(-1)`. Actual installed-Vosk subprocess tests were
observed failing on fd 2 output before the correction. The shared loader now uses
`-4`, below all Vosk handler severities. Runtime tests verify sanitized preparation
for empty/corrupt local models and a real native sample-rate decode error using
generated PCM silence. They skip cleanly when the optional Vosk dependency or
local model fixture is absent. Generic Kaldi option usage can bypass the handler;
the benchmark CLI therefore runs the same decoder in a bounded child and discards
native stderr, forwarding only validated timing/environment metadata.

All 138 tests, Ruff and the isolated Gio protocol check pass after the change.
The actual benchmark was rerun through the child wrapper: the same 8.308-second
fixture still yields 65 blocks and 63 partial calls; model load 0.786 s, decode
1.480 s, realtime factor 0.178, p50/p95/max blocks 5.69/69.63/439.64 ms and finalization
26.14 ms. Metric boundaries remain inside the child; timing variation does not
establish a speedup from isolation. No microphone or host portal was accessed.

Task 2b specification and quality reviews approved the realtime speech work and native-diagnostic correction (`ce91224`). The independent quality recheck passed all 138 tests, including actual Vosk subprocess stderr tests.


## Task 2c: custom shortcuts and safe edit core

Commits `7ecbb68` and `eddb873` implement the bounded custom phrase/chord catalogue,
immutable reviewed key plans, staged editing, transactional v1→v2 database upgrade,
configuration CRUD, main-thread controller management and isolated practice output.
New behavior was observed RED before production implementation, then GREEN.

On 25 October 2026 the full command
`PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v` passed **168 tests**.
`.venv/bin/ruff check src tests scripts` passed. The private
`PYTHONPATH=src .venv/bin/python scripts/check-portal-protocol.py` passed real Gio
request/response, keyboard-only options, Unicode events, shortcut events and
revocation against an isolated fake D-Bus service. Added tests cover direct portal
chord validation and modifier release on errors/cancellation, normalization and
collisions, custom two-stage approval, staged empty/invalid edits, stale IDs,
global-confirm disarming, catalogue cancellation during capture/countdown/input,
SQLite constraints/rollback/corruption/future versions, preservation of every
legacy preference and practice preview isolation. A wheel build includes both
new-schema and migration SQL resources.

No GUI, host keyboard permission, microphone or real desktop input was started
for this milestone. Native controls and on-screen chord/risk review are the next
integration task. Independent specification and code-quality reviews approved this backend milestone; this evidence does not claim hardware compatibility.


Task 2c quality-review follow-up reproduced and corrected stale-controller
item updates that could overwrite another controller's shortcuts. Real shared
SQLite regressions now cover adds, updates, deletes, unknown-to-cache IDs,
preflight validation, safe storage failure and activation of the authoritative
returned catalogue. Reset now revokes/disarms before any database reset and
preserves old configuration safely on storage failure. These three new tests
were observed RED before the corrections; the complete suite passes **171 tests**,
with Ruff and the isolated Gio protocol check passing again.

Task 2c passed independent specification and code-quality reviews. Final backend verification: 171 tests, Ruff, and isolated real-Gio protocol tests pass. User-customized voice phrases and validated single-chord actions use a transactional SQLite v1→v2 migration that preserves every existing preference. The desktop GUI is the next milestone.

## Task 3: native app and distribution

Recorded 25 October 2026. The native GTK4/libadwaita app now runs with Voice,
Commands and Setup views. It starts in isolated typed Practice; selecting Live
still requires explicit saved mic consent, successful model preparation and an
actual keyboard grant before capture. UI and controller regressions were observed
RED before implementation/corrections and then GREEN. These include readiness,
immutable action details, staged editing, custom CRUD/collisions/disabled entries,
second confirmation, focus countdown, Stop/Escape cancellation, mode revocation,
actual returned binding descriptions, optional dependency recovery and read-back
subprocess lifetime. Source/wheel icon lookup is asserted.

Fresh integrated command:

```sh
WVC_GTK_TESTS=1 GDK_BACKEND=x11 GSK_RENDERER=cairo GTK_A11Y=test GIO_USE_VFS=local \
  PYTHONPATH=src dbus-run-session -- xvfb-run -a .venv/bin/python \
  -m unittest discover -s tests -v
```

**203 tests passed, no skips**, including **23 native GTK cases** on this host.
The real native Vosk regression cases used the optional engine/model fixture
already installed for prior milestones. The separate pure discovery run before
the last presentation test passed with native cases explicitly skipped; CI runs
them in a separate Xvfb step. No host microphone or live input adapter is used by
the GTK tests. The real-space duration-cap regression uses libXtst key events on
only the private Xvfb display: physical release clears the latch, auto-repeat does
not restart capture, and a newly focused hold works afterward. Tests also assert
that every view is attached to the native window, programmatic labels are set,
and long phrases/choice labels do not force wide controls.

The following fresh checks passed:

- `.venv/bin/ruff check src tests scripts`
- `.venv/bin/python -m compileall -q src tests scripts`
- `PYTHONPATH=src .venv/bin/python scripts/check-portal-protocol.py`
- `.venv/bin/python -m build --no-isolation` (wheel and sdist)
- `bash -n scripts/install-local.sh scripts/run-local.sh`

The local installer was executed with an isolated `XDG_DATA_HOME` under ignored
`artifacts/`, verifying the quoted absolute launcher command and exact matching
hicolor SVG bytes without changing the user's application menu. The wheel was
installed into a fresh system-site-packages venv; from `/tmp`, installed CLI help,
commands, read-only diagnostics, SQL/schema/desktop/icon resources and the actual
native application were checked. This venv had no Vosk or model: native startup
and typed Practice review succeeded and the bundled icon resolved. Its app was
closed normally to exercise shutdown.

Actual native windows were rendered and inspected at 780×820 and 550×820 in
Practice, including Voice, Commands and Setup, system dark appearance and a light
appearance with a larger `Sans 16` font. Text and long command buttons wrap, views
scroll, and Stop remains outside the scrolling content. Screenshots are ignored
local artifacts, not recordings or real desktop compatibility evidence. Toolkit
startup on the private D-Bus activated portal services without requesting live
keyboard/microphone grants. Host PyGObject emitted upstream Python 3.14
DeprecationWarnings and Xvfb emitted software-rendering/portal-backend notices;
these did not fail the checks.

The Linux CI workflow is configured for pure tests, real GTK/XTest cases,
protocol integration, static checks, distribution build and installed entry-point
inspection. GitHub Actions passed all jobs for commit `dcc7eb5`, including the
installed entry-point checks ([run 40237283310](https://github.com/K-Arthur/wayland-voice-control/actions/runs/40237283310)).
Final independent specification and code-quality reviews approved commit
`ab6cc25`; fresh review verification also passed all 203 tests, Ruff, compileall,
isolated Gio protocol checks and wheel/sdist builds.

Still unperformed: real GNOME permission dialogs, grant denial/revocation by the
compositor, actual text/Unicode delivery into another application, global shortcuts
on the user's real desktop, physical microphone capture/lifetime/latency, Orca
usability and sessions with intended voice-input users. These remain the manual
release gates and are not implied by any of the software checks above.

### Task 3 integrated review corrections

Final code-quality review reproduced two UI-boundary defects: unsaved Setup
changes could leave saved microphone consent/live grants active, and releasing
Space after a duration cap while focus had moved elsewhere could strand the local
hold latch. Three focused tests were observed failing before correction: immediate
mic-consent revocation, every Setup field pausing authority across mode switches,
and actual XTest cap→focus move→key-up→cancel→new focused hold.

Every editable Setup change now immediately cancels work, revokes runtime
microphone consent and live/shortcut grants, and resets readiness without saving
the draft. Unsaved status remains visible and the draft survives Practice/Live
switches. Hold, preparation, Connect and shortcut-binding actions remain gated
until Save; Save still requires explicit preparation/reconnection. Direct
`shortcut_event('hold_to_talk', True)` and local hold calls cannot capture in that
paused state. A capture-phase window key-release handler receives release even
when focus has moved away from the talk button.

Fresh integrated verification after these corrections passed **202/202 tests**,
including **22 GTK tests**, with the same private Xvfb/D-Bus command above. Ruff,
compileall, isolated real-Gio protocol verification and wheel/sdist builds also
passed. No new hardware/real GNOME validation is implied.

The final hold-ownership regression additionally moves real XTest keyboard focus
to a separate mapped X11 top-level after the duration cap and releases Space
there. It was observed RED with the original latch still true. Top-level window
deactivation now cancels active held capture and unconditionally abandons its
physical press ownership, including when a cap has already ended capture. The
same-window auto-repeat guard remains intact. Returning focus and making a new
genuine Space press is verified with real private-display events.

Fresh checks after that correction pass **203/203 tests**, including **23 GTK
tests**, plus Ruff, compileall, private real-Gio protocol checks and wheel/sdist
builds. This extends headless event-routing evidence; real GNOME input and
microphone validation remain unperformed.

## Sustained offline speech recheck

Using the existing public Vosk upstream WAV fixture and the local
`vosk-model-small-en-us-0.15`, the isolated benchmark decoded 58.156 seconds
formed by repeating the 8.308-second WAV seven times. Unpaced decode took 4.004
seconds (0.069 realtime factor); paced replay took 4.760 seconds total decode
time (0.082 realtime factor) and measured 383 ms maximum accumulated replay
lag. This used no microphone, network or transcript output. Repeated sentence
boundaries make it a throughput stress check, not representative speech or
accuracy evidence. See [performance.md](performance.md) for chunk timings and
measurement limits. Physical microphone end-to-end latency and recognition
accuracy remain unverified.

## Initialization and CI hardening

The GUI now relies on default single-instance `Adw.Application` behavior so
repeated launches activate the existing window rather than creating parallel
microphone/shortcut sessions. GitHub CI explicitly grants `contents: read`,
checkout does not persist credentials, and checkout/artifact actions are pinned
to verified full commit SHAs with Dependabot update checks. Safe startup and
remaining trust boundaries are documented in [security.md](security.md).

Validation on 25 October 2026: 211 Python tests pass (32 expected skips for
opt-in GTK and unavailable optional Vosk/model fixtures); all 29 isolated native
GTK tests pass under Xvfb/D-Bus; Ruff, compileall, YAML structure/permission
checks and `git diff --check` pass. The GTK suite validates widgets and startup
factory isolation; it does not launch two separately registered desktop app
processes or verify behavior in a real GNOME session.

## Coexistence with other voice applications

The capture stream is now explicitly categorized as PipeWire `Audio/Capture`
with the `Accessibility` role and carries the application and stream names
`Wayland Voice Control` and `Voice Control microphone capture`. A PipeWire graph
check using `--target=0` confirmed these properties without linking a microphone.
Setup warns that capture is shared and advises pausing other voice/dictation
apps. Partial portal shortcut grants now show every missing action as unbound
with a local-control fallback. The manual checklist covers simultaneous audio
capture, shortcut conflicts and interleaved keyboard input; those real-app
conflict cases still require validation in a desktop session.

Fresh validation: 214 Python tests pass (34 expected skips), all 31 isolated GTK
tests pass, and Ruff, compileall, the private Gio portal protocol check and
`git diff --check` pass. The Setup view was visually inspected at 780×900 under
Xvfb; the shared-microphone warning wraps visibly beneath the consent control.
PipeWire exposed the app identity and capture/communication properties while an
unlinked `--target=0` recorder was running; no microphone was used.

## Resident desktop controls

The resident lifecycle and Controls1 API were implemented in `1f727f6` and passed
separate spec and code-quality review. On the CachyOS development host (GTK 4.24,
Python 3.14), the pure discovery run passed 230 tests with 46 native/optional cases
skipped; an isolated D-Bus/Xvfb run with GTK tests enabled passed the same 230 tests
with only three optional Vosk cases skipped. The checks include actual Gio
cross-connection methods/signals, no-argument protocol rejection, transcript-free
status, saved-Setup/capture readiness, controller replacement, capture-source
ownership, normal/background close, second-process activation, cold hidden
Practice startup and a Quit reply received before clean process exit. Ruff,
compileall and whitespace checks passed for the change.

A real native screenshot at 560×820 caught a wrapping Quit label; the corrected
64×44 minimum button uses a single-line label. The enlarged background option
wraps within the available area, and the Setup section/header show no clipping.
This was rendered in isolated Xvfb with fake live adapters. It does not establish
GNOME focus policy, portal grants, real microphone capture or Orca usability.

## KDE widget and final desktop-controls validation

Implementation: `f747fbc`, with the successful-Quit refresh regression fixed in
`5b67a04`. Final review found a test-only helper registration race;
`043fa3f` registers that helper synchronously after startup and binds calls to
the captured unique owner, matching the production bridge. Eight consecutive
full protocol runs then passed; no production API was changed for the fixture. The old real-portal fixture also exposed its three-binding assumption
when Show controls added a fourth binding; `deee1f2` checks all four exact IDs,
returned descriptions and release/repeat filtering on the actual Gio wire.

Fresh final checks on CachyOS, Plasma workspace QML module 6.7.5, Qt/QtTest 6.12.0,
Python 3.14 and GTK 4.24:

- Pure discovery: **235 tests, 46 skipped**, all remaining cases passed.
- Full GTK-enabled discovery on private D-Bus/Xvfb: **235 tests, 3 optional Vosk
  cases skipped**, all remaining cases passed. No host microphone/input used.
- Native KDE desktop-style Qt Quick Test: **21 passed, no skips**. Covers
  readiness, duplicate calls, emergency controls during another pending call,
  typed D-Bus values, stale replies, service loss, version rejection, keyboard and
  accessible names, compact recording state, native padding and large-text scroll
  reachability. A successful Quit no longer reads the disappearing service.
- Real GTK–QML protocol: **3 passed, no skips** (one lifecycle scenario plus
  setup/cleanup), using actual Controls1 and the installed KDE D-Bus QML module.
  A separate observer attaches to an already-running service. The private bus
  activates the app through a launcher whose absolute filename contains spaces,
  quotes, dollar signs, backticks and backslashes; recording/review use injected
  fake devices. It verifies cold Practice, Start/Finish/review, Cancel/Stop,
  crash/restart with a new owner, Quit, activation failure and no idle activation.
- The actual `.plasmoid` archive installed and upgraded through `kpackagetool6`
  and loaded in `plasmawindowed`, using temporary XDG directories and a private
  bus/display. No user panel, login startup or shell was modified.
- Ruff, compileall, Bash syntax, diff checks and both private protocol checks
  passed. Wheel/sdist and the deterministic widget archive build passed; all
  widget metadata/QML and the matching service are included in distributions.
  A temporary installed-wheel environment verified all five QML files, metadata,
  the service and CLI help/commands/doctor without creating configuration.

Visual review used the actual native package at 360×500, plus independent
Wayland own-window captures at 360×520, 240×320 and 320×480 with normal, 200% and
400% text. Standalone layout captures used Qt's Basic style and explicit
light/dark palettes; native KDE style was checked separately through QtTest and
`plasmawindowed`. The compact recording control was also captured through native
QtTest on Wayland. At 400%, initial action labels were ellipsized; the shared
wrapped ActionButton fixed them and a regression now checks full labels and
scroll/click reachability of Quit. Native ScrollView required explicit padding
on all four sides. No remaining clipping was found in those reviewed layouts.
Local, ignored evidence files are under `artifacts/`: `widget-plasma-preview.png`,
`widget-ready-light.png`, `widget-recording-dark.png`, `widget-offline-narrow.png`,
`widget-practice-large.png`, `widget-400-bottom.png`,
`widget-compact-recording.png` and `background-setup-560.png`.

These checks establish the implemented widget/lifecycle/protocol behavior in the
listed environments. They do not establish GNOME panel integration, real portal
keyboard insertion, physical microphone latency/accuracy, Orca/braille output,
or usability with disabled participants. The existing manual matrix remains
required; no TalkBack parity or broad disability-optimization claim is made.

## Main integration

The completed desktop-controls feature was fast-forward merged and pushed to
`main` at `25ba3be`. The merged checkout passed the full GTK-enabled 235-test run
(three optional Vosk cases skipped), 21 native KDE tests, the three-case actual
GTK–QML scenario, the real Gio portal check, static checks and all three build
artifacts. [Public main-branch CI passed](https://github.com/K-Arthur/wayland-voice-control/actions/runs/40272285201),
including installed entry-point checks and distribution upload. The source
worktree was removed after copying local visual evidence to the main checkout's
ignored `artifacts/` directory. The main checkout retains the built `.plasmoid`,
wheel and sdist in ignored `dist/`.


## Portal lifecycle and actual accessibility transport follow-up

The full-system audit reproduced two additional implementation faults, then
observed failing regressions before fixes: service disappearance left keyboard
permission/bindings apparently active, and `ShortcutsChanged` never updated
returned bindings. Commits `aa26c0f` and `a7eaebe` invalidate requests/sessions on
portal owner loss or direct replacement, reject stale grants, suppress cleanup
and input autoactivation, and merge the portal's partial binding updates. A
binding change cancels held global/pending work without synthesizing confirmation
or stopping an unrelated local/widget recording. Omission from a partial update
does not establish removal. Explicit reconnect/review is required after loss.

Fresh native/private-bus discovery passed **249 tests, no skips**, using the
already installed Vosk environment and local public model fixture. The existing
model directory was temporarily linked for fixture reads and the link removed afterward;
no microphone or host keyboard input was used. The default environment without
the speech dependency still runs the pure suite with its documented optional
skips. The extended actual Gio fixture passes owner disappearance, direct
replacement, pending-session loss and late responses, as well as partial binding
updates and held-confirm suppression. Native Qt Quick tests pass **21 tests**;
actual GTK/widget protocol passes **3 tests**. Ruff, compileall, shell syntax,
widget archive and Python wheel/sdist builds pass.

Commit `a59d9f2` adds `scripts/check-accessibility.py`. Unlike `GTK_A11Y=test`, it
uses real GTK AT-SPI export and libatspi interfaces on an activation-free private
D-Bus with an explicitly launched registry and Xvfb. It checks selected names,
roles, disabled capture/default consent, complete synthetic Practice text,
edit/re-review approval invalidation, simulated dictation, custom shortcut
creation and separate risky approval/cancel, Setup headings and accessible Quit.
The completed script passed three consecutive runs and a final recheck. GTK can
replace command rows during traversal; bounded lookups retry stale remote object
paths, while actions are never automatically retried. CI runs this check with
distribution AT-SPI dependencies. This supersedes the earlier transport-testing
limitation for these isolated Practice paths; no Orca, braille, switch-scanning or
intended-user usability result follows.

A new paced public-fixture benchmark measured model load 0.763 s, decode 1.797 s
for 8.308 s of audio, realtime factor 0.216, 434.82 ms maximum replay lag and
35.69 ms finalization. This is repeatable decoder evidence, not a physical
microphone latency or accent/speech-disability accuracy result. See performance.md.
The shortcut-change status was visually checked in the rendered 560×820 native
window; its instructions wrap without clipping and Stop/Quit remain visible.
The delayed user report that windows opened/closed did not confirm the requested
scratch-field text, so live insertion remains unverified.


### Cross-distribution accessibility validation

The first Ubuntu 24.04 actual AT-SPI run failed the section-group assertion.
Comparing stable numeric roles retained the failure: the named section exported
PANEL rather than GROUPING. Inspection of the exact official Ubuntu source
package `gtk4_4.14.5+ds-0ubuntu0.10` established that this is intentional:
`a11y-Fix-A11Y-groups.patch`, included in the patch series, maps GTK GROUP to
AT-SPI PANEL so Noble's older Orca announces group labels correctly
([Ubuntu bug 2119005](https://bugs.launchpad.net/ubuntu/+source/gtk4/+bug/2119005)).
It was not evidence that the app had lost its semantic group. The actual-wire
check now permits only these two documented group mappings, retaining exact
section names/headings; native GTK checks still require GROUP.

Commit `71a0fac` also removes reliance on post-construction class-default role
setters by assigning each semantic widget's instance `accessible_role` property
first during construction. A fresh-process regression was observed failing with
a legacy class setter unable to update instances, then passing with constructor
properties; ordinary labels/boxes retain their roles. This is initialization
hardening, and did not itself resolve the Ubuntu mapping mismatch. Fresh native discovery passes **250 cases with no skips** using the existing
optional speech environment/model fixture. The actual local AT-SPI workflow
also passes.

A separate Ubuntu 24.04 runtime with GTK 4.14.5/PyGObject 3.48.2 was reproduced
inside an unprivileged bubblewrap filesystem/user/PID namespace using temporary
files, without installing system packages on the host. An instrumented synthetic
entry had 17 characters; `GetText(0,-1)` returned length zero while
`GetText(0,CharacterCount)` exactly matched the set text. The harness now uses
explicit complete ranges. GTK 4.14 intentionally prohibits an accessible name
for STATUS; the status Text interface exposes the current state, so the harness
checks that full content and its privacy boundary instead of expecting a name.
The complete Practice accessibility workflow passes in that Ubuntu runtime.
The provisional explicit-status-name change was reverted after this evidence;
it did not solve the compatibility issue and is not part of the final source.
Public Ubuntu CI passed every stage for `0a1a809`, including the actual AT-SPI
workflow, private portal protocol, native widgets, distributions and installed
entry-point checks ([run 40277407475](https://github.com/K-Arthur/wayland-voice-control/actions/runs/40277407475)).
This closes that software portability gate, not the manual GNOME/microphone/Orca
or intended-user release matrix.
