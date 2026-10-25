# Local speech performance

The application decodes speech incrementally on its capture worker. The shared
`StreamingDecoder` consumes up to 4096 bytes of mono 16 kHz signed 16-bit PCM per
call: a full block represents 128 ms of audio. It combines completed Vosk segments
with the current `PartialResult` for a provisional display, replacing the partial
rather than appending it. Final review text contains completed segments plus
`FinalResult`, never an unfinished partial. Both paths have a 4000-character bound.

Vosk describes its [streaming API](https://alphacephei.com/vosk/); the official
[microphone example](https://github.com/alphacep/vosk-api/blob/master/python/example/test_microphone.py)
shows the `Result`/`PartialResult` distinction. This application keeps PCM in a
pipe/in memory and does not implement the example's optional recording-to-file path.

## Reproduce without a microphone

With local dependencies, an extracted local model and a local WAV already present:

```sh
PYTHONPATH=src .venv/bin/python scripts/benchmark-speech.py \
  --model models/vosk-model-small-en-us-0.15 \
  --wav models/vosk-upstream-test.wav

# Replay blocks at their audio arrival times and measure accumulated decoder lag:
PYTHONPATH=src .venv/bin/python scripts/benchmark-speech.py \
  --model models/vosk-model-small-en-us-0.15 \
  --wav models/vosk-upstream-test.wav --paced
```

The tool accepts uncompressed mono 16 kHz 16-bit WAVs between zero and 60 seconds
(excluding zero), validates the declared format/length and detects truncated PCM.
It reads bounded blocks through the application's actual streaming decoder. It
opens no microphone, uses no network, creates no audio copy and prints no
transcript. Failures print a fixed message without dependency tracebacks/content.
The model and WAV must be supplied separately; runtime does not download them.

`cold_load_seconds` measures loading a model in a new process, including the first
Vosk import, with potentially warm OS filesystem caches. `decode_seconds` sums
per-block accept/result/partial JSON processing plus finalization. File reading,
recognizer creation and pacing sleeps are excluded. `realtime_factor` is that
decode time divided by WAV duration: below 1 is necessary for average throughput
to keep up, and below 0.5 is the small-model target on the development host.
Chunk p50/p95 use nearest-rank percentiles. `finalization_seconds` measures the
shared decoder's `finish()` call. `partial_count` counts actual `PartialResult`
calls, including empty or unchanged partials, rather than UI updates.

For paced replay, `max_replay_lag_seconds` is the maximum time from a block's
scheduled arrival (the end of its audio interval) until its decode finishes.
It includes accumulated prior decode backlog and scheduler delay, excludes cold
loading, and is separate from finalization. Unpaced chunk costs do not by
themselves measure live backlog.

## Measurements, 25 October 2026

AMD Ryzen 7 3750H with Radeon Vega Mobile Gfx; CachyOS/KDE host,
Linux 7.2.9-2-cachyos x86_64, glibc 2.44; Python 3.14.8; Vosk 0.3.45;
`vosk-model-small-en-us-0.15`. The public upstream fixture has 8.308 seconds of
speech (65 blocks, 63 partial calls). Each row is a separate process on the same
host, not a statistically representative hardware sample.

| Run | Model load (s) | Decode (s) | Realtime factor | Chunk p50 (ms) | Chunk p95 (ms) | Max chunk (ms) | Finalize (ms) | Max paced lag (ms) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Unpaced 1 | 1.981 | 3.336 | 0.402 | 13.64 | 132.30 | 1244.70 | 59.58 | — |
| Unpaced 2 | 1.588 | 3.450 | 0.415 | 10.18 | 193.76 | 817.81 | 64.92 | — |
| Paced | 1.753 | 2.176 | 0.262 | 7.59 | 107.26 | 644.45 | 44.62 | 644.55 |

Average decode throughput meets the host target, while individual bursts can
still delay drafts for roughly 0.6–1.2 seconds on these runs. Paced replay observed
about 645 ms maximum accumulated lag. Measurements vary with load, scheduling and
power state. These are local decoder throughput/replay measurements; they do not
establish end-to-end physical microphone latency, compositor input latency,
speech accuracy, or realtime performance on other hardware/models/languages.

## Responsive UI and startup

An explicit model-prepare setup action loads/caches the model on the same excluded
worker used for capture. It requests no microphone/keyboard permission and starts
no recorder. First-use capture can also load the model; releasing while loading
prevents late recorder startup. Successful preparation removes repeated model
loading from subsequent captures. Each capture has a fresh recognizer.

Draft dispatch has one pending mailbox, replacing its bounded text while the UI
is stalled. Updates are limited to about five per second, including after a
stalled dispatcher resumes. Release, finalization, failure and cancel clear pending
draft data; generation guards discard stale callbacks. Model work and recognizer
work run off the UI thread, so decode bursts do not block native controls. Drafts
are display-only and can never create, approve or execute an action.
