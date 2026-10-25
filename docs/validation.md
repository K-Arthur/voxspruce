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
- Vosk's public [upstream test WAV](https://github.com/alphacep/vosk-api/blob/master/python/example/test.wav), processed locally, produces the expected opening and closing digit sequences. This checks the decoder and model, not microphone capture, word-error rate, accent coverage or application integration.
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

**200 tests passed, no skips**, including **20 native GTK cases** on this host.
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
inspection. No remote GitHub Actions run is claimed here. UI specification review
approved the tested behavior after corrections; the final integrated code-quality
review is tracked separately in the implementation plan.

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
