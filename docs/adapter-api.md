# Coordinator and operating-system adapters

`Controller` is the native UI boundary. Create it on the GTK thread with validated
`Settings`, a `RemoteDesktop`, an `AudioCapture`, and the `dispatch` and `schedule`
functions from `gio_transport`. Pass a `SettingsStore` for preference updates.
`RequestTransport(GioWire())` supplies the portal transport. Construction does
not request permission, capture audio, bind shortcuts, or send input.

Every public coordinator call and observer callback belongs on that same UI
thread. Workers send completions through the dispatcher. Each asynchronous
action has a generation; both success and failure are ignored after cancel,
stop, valid edit, or replacement. Permission requests have separate attempt
identities: cancel closes unfinished requests, while unrelated action changes
do not hide a completed binding. This gate must precede untagged
`Workflow.complete_execution()` and `Workflow.fail()` calls.

`subscribe(callback)` immediately supplies an immutable `Snapshot`, then supplies
updates; its return value unsubscribes. `snapshot` exposes state, immutable pending
action, status, error, microphone activity (`loading`, `recording`, `processing`,
`idle`), remaining countdown seconds, permissions, practice flag, and actual
shortcut binding descriptions. The countdown reports the remaining delay; a UI
may round it upward for display. Do not infer microphone activity from workflow
`RECORDING`: the model may still be loading.

- `connect(parent_window="")` explicitly asks the desktop for keyboard access.
- `set_mode(Mode)` changes Dictation/Commands and cancels existing work.
- `start_recording(mode=None)` begins a held capture using the selected mode;
  `finish_recording()` releases it. False means capture did not start; display
  the snapshot status. Duration-cap completion also finishes the workflow.
- `edit(action_id, text)` revokes approval and creates a new review identity.
- `confirm(action_id, source="local")` performs only the first confirmation.
  `confirm_second(action_id)` is a separate UI action for risky commands. Bind
  it to a separately labeled control, never to the first-confirm handler.
- Local confirmation uses the configured visible focus delay. A global
  confirmation uses a short release settle because the user already selected
  the destination. Input runs off the UI thread and never retries automatically.
- `cancel()` discards capture/content/timers and cancels input. `stop()` additionally
  closes desktop and shortcut permission sessions. `reset_error()` explicitly
  clears an error. `update_settings(mapping)` / `reset_settings()` persist validated
  preferences and cancel/revoke work before applying the returned settings.
- Optional `GlobalShortcuts` is wired automatically when passed to the coordinator.
  `connect_shortcuts()` explicitly binds it. Granted subsets and actual trigger
  descriptions are exposed. Hold-to-talk starts on press and finishes on release;
  confirm/cancel fire only on release. Global confirm cannot perform stage two.

For a separate practice coordinator, supply `remote=PracticeInput()` and
`practice=True`. Only `review_text(text, mode)` creates examples. Capture is
rejected even when saved microphone consent is enabled, and shortcut adapters are
ignored. This no-op adapter has no portal or desktop transport. Live
`review_text` calls are rejected.

`AudioCapture.start` validates explicit microphone consent and a local existing
model directory, then loads only `vosk.Model(path)` on a worker. Releasing during
load prevents recorder startup. Normal release terminates the recorder and drains
at most 64 KiB of already queued PCM without waiting before final recognition.
Cancellation discards queued callbacks. Recognizer/content is per-capture; only
the model is cached. New capture is excluded until previous child cleanup ends.

`doctor [--json]` performs read-only introspection/property checks and reads an
existing settings DB without creating one. Capability availability is distinct
from permission or compositor compatibility. `commands` prints the fixed allowlist.
The default CLI entry lazily imports the native app.

`PYTHONPATH=src .venv/bin/python scripts/check-portal-protocol.py` verifies the real
Gio wire against a fake service inside a private `dbus-run-session`. It records
key events in memory and never touches the host portal, compositor, or microphone.
The separate real-session checklist still requires manual GNOME/microphone tests.
No standalone live fixed-text portal test is provided; live validation currently
uses the speech path and its normal review/confirmation flow.

## Streaming drafts and explicit model preparation

`Snapshot.draft_text` is an in-memory provisional string (up to 4000 characters).
Render it read-only while recording; it may change or disappear and must never be
copied into `Workflow.receive_transcript`, a pending action, or an approval call.
`finish_recording()` clears it immediately and waits for the final review result.
Processing/final result/failure/cancel/stop/settings changes also clear it. The
final transcript still enters only through the gated final-result callback.

`Snapshot.model_readiness` is `idle`, `loading`, `ready` or `error`. Call
`Controller.prepare_model()` from the setup button. It returns true when accepted;
false means practice mode, an invalid path or previous speech work still stopping
(check snapshot status/error). It cancels pending action work, loads only the
existing local `settings.model_path` on a worker, and requests neither microphone
nor desktop permission. A stale completion cannot affect newer work. Successful
readiness survives ordinary cancel/stop because the model remains cached; applying
settings invalidates readiness and requires explicit preparation again. First-use
capture also reports loading/ready/error. Practice prohibits both preparation and
capture. Native controls can require readiness, explicit microphone consent and
keyboard permission before enabling held live capture.

Direct adapter API:

- `AudioCapture.prepare(model_path, *, on_state, on_error) -> bool` emits `loading`
  then `ready` or `error` via its dispatcher; errors contain only fixed application
  messages. An invalid local path raises `AudioError` before worker creation.
- `AudioCapture.start(..., on_draft=None)` adds an optional provisional callback;
  existing final `on_result` and activity/error callbacks retain their meanings.
- Preparation and capture share one worker exclusion and one model cache. Busy
  calls return false. Cancel invalidates queued success/error/readiness/draft
  callbacks immediately; worker exclusion lasts until old cleanup completes.
- Draft callbacks are coalesced through one bounded mailbox and throttled to at
  most approximately five updates/second with an injectable monotonic `clock`.
  A stalled UI cannot accumulate one draft callback/string per PCM block. Release
  suppresses queued drafts, while final recognition drains only the bounded PCM
  already described above.

See [performance.md](performance.md) for reproducible offline benchmarks and the
limits of the observed throughput/latency evidence.
