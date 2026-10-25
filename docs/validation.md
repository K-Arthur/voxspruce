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
