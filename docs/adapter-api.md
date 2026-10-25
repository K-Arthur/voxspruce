# Coordinator and operating-system adapters

`Controller` is the native UI boundary. Create it on the GTK thread with validated
`Settings`, a `RemoteDesktop`, an `AudioCapture`, and the `dispatch` and `schedule`
functions from `gio_transport`. Pass a `SettingsStore` for preference updates.
`RequestTransport(GioWire())` supplies the portal transport. Construction does
not request permission, capture audio, bind shortcuts, or send input.

Every public coordinator call and observer callback belongs on that same UI
thread. Workers send completions through the dispatcher. Each asynchronous
operation has a generation; both success and failure are ignored after cancel,
stop, edit, or replacement. This gate must precede untagged
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
