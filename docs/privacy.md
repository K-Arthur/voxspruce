# Privacy and permission model

The application runs recognition locally. Runtime code has no account, telemetry, upload, cloud-recognition fallback or automatic model download. Installing Python packages and obtaining a speech model are separate setup operations that use the network.

## Audio and text

A fresh process defaults to isolated typed Practice; no live capture or portal adapters are constructed. Selecting Live still leaves the microphone off. App-level microphone consent must be enabled and saved, then the user must explicitly activate a capture control. Hold-to-talk ends on release; the alternative start/stop control ends on a second activation. Both stop at the configured duration cap, and capture never starts on launch. Any unsaved Setup change immediately revokes runtime microphone consent and live grants; capture and new grants remain paused until Save followed by explicit preparation/reconnection. PipeWire audio is streamed through a pipe to a local Vosk recognizer. The application does not write audio files. Transcript and pending-action text live in memory, are displayed for review, and are discarded on cancel, completion or quit. The clearly marked last simulated Practice output remains visible in memory until replacement or leaving Practice; it is never saved. Python, Vosk and the operating system may retain freed memory or swap pages; this is not a secure-memory or forensic-erasure guarantee.

Persistent SQLite storage contains only validated preferences such as model path, microphone consent, time limits and theme, plus intentionally configured custom shortcut IDs, phrases, single chords, descriptions and enable flags. No recognized transcript, audio, clipboard content, pending action, permission token or activity history belongs in the database. Custom phrases are entered configuration, never automatically saved speech. The application creates private configuration storage and can atomically reset preferences and remove every custom shortcut. The model files themselves remain on disk until the user removes them.

## Desktop input

The RemoteDesktop portal requests keyboard control. The desktop presents its own permission dialog; the app checks the returned grant before allowing input. Permission is not restored from a saved token. No screen capture is requested. Desktop denial, revocation or session closure blocks future input. Emergency stop closes the session and cancels work. The app never uses raw input-device access, root, uinput or input-helper daemons.

The app uses PipeWire capture after its own explicit mic-consent step. This step is an application setting, not a claim that Linux exposes a universal microphone-consent portal. The operating system's own audio/device restrictions continue to apply.

PipeWire capture is shared audio routing, not an exclusive microphone lease. Another permitted voice-typing or meeting app can receive the same microphone concurrently. PipeWire's session manager routes capture streams based on their stream/device metadata ([capture stream and linking policy](https://pipewire.pages.freedesktop.org/wireplumber/policies/linking.html)). This app labels its stream as `Wayland Voice Control` with the `Accessibility` role so desktop audio tools can identify it; it does not stop or enumerate other apps. Pause other voice/dictation apps when duplicate recognition or unintended capture would be a problem, and use the desktop microphone indicator where available.

Optional read-back pipes only the currently reviewed action to local espeak-ng stdin, never through command arguments, a shell or a file. Cancelling, editing, confirming, replacing an action, changing settings/mode or quitting terminates that read-back process.

Global shortcuts use the desktop portal and its consent UI. The portal may return only a subset when a requested trigger is unavailable or not accepted ([GlobalShortcuts portal](https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.GlobalShortcuts.html)). Setup lists every requested binding and marks missing ones as unbound; use the local controls for those actions. The app does not monitor arbitrary keys. Users may decline this permission and use the local controls.

## Confirmation and limits

Dictation and command modes are separate. Every action is reviewed and confirmed; commands capable of submission or destruction and all custom shortcuts require another distinct confirmation. Dictation cannot contain injected Enter/Tab or other control characters. Unknown commands are rejected. Confirmations expire and are single-use, and starting an edit invalidates previous approval immediately, even while the editor is empty or invalid. Re-review explicitly creates new approval work. Custom shortcut changes cancel current capture, edits, approvals and countdowns.

The portal cannot attest which application's field receives input. The user chooses the destination. Another voice-control tool may also inject into the focused app; pause it before confirming here to avoid competing input. App-specific keyboard behavior, clipboard contents, focus changes and partial failures remain relevant: this software does not claim that an approved action can never have unintended effects. A failed insertion must not be retried automatically.

This is an experimental community tool, not certified assistive technology. The GNOME compatibility test and accessibility testing with intended users are required before a stable support claim.

Live draft text is provisional, bounded and display-only. Partial results never
enter the action/confirmation workflow; release clears the draft before final
review. A stalled UI retains one bounded draft mailbox, rather than a transcript
history or one callback payload per audio block. Cancel, finalization and failure
clear pending draft data. Explicit model preparation loads only the local model
off-thread and starts no microphone process, so it needs no microphone consent
or keyboard grant. The offline speech benchmark reads only a user-supplied local
WAV/model, prints timings without transcripts, and writes no audio or content.


## Native speech diagnostics

The shared model loader sets Vosk's native verbosity to `-4`, below assertion
(`-3`), error (`-2`), warning (`-1`) and informational (`0`) severities. The earlier
`-1` setting suppressed informational messages while still exposing native error
messages, including model paths. This uses Vosk's own logging threshold and does
not redirect process-wide stderr in the multithreaded desktop application.
The mechanism is defined by the pinned [Vosk 0.3.45 log handler](https://github.com/alphacep/vosk-api/blob/v0.3.45/src/model.cc)
and [Kaldi severity definitions](https://github.com/alphacep/kaldi/blob/vosk/src/base/kaldi-error.h).

Native libraries are not a security sandbox: Kaldi can print generic option
usage outside that handler, and supplied model configuration can change native
logging settings. Application callback errors remain fixed messages. The
standalone benchmark additionally discards its dedicated native child's stderr,
bounds/validates success metadata and never forwards native tracebacks or content.
Actual subprocess tests capture native file-descriptor output; Python
`redirect_stderr` alone cannot verify this boundary.

## Background and panel status

Background operation never means idle microphone listening. The optional desktop
widget receives only protocol version, Practice/Live, workflow/microphone/model
states and readiness/visibility booleans. It receives no draft, transcript,
command phrase, path or free error message. Generic review notifications contain
no content. Explicit widget Start uses the same consent/readiness/duration gates
as the main app; Stop and Quit close live grants. The same-user session-bus trust
boundary is described in [desktop controls](desktop-controls.md).
