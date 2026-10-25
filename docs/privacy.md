# Privacy and permission model

The application runs recognition locally. Runtime code has no account, telemetry, upload, cloud-recognition fallback or automatic model download. Installing Python packages and obtaining a speech model are separate setup operations that use the network.

## Audio and text

The microphone is off at launch. App-level microphone consent must be enabled, then a push-to-talk control held. PipeWire audio is streamed through a pipe to a local Vosk recognizer. The application does not write audio files. Transcript and pending-action text live in memory, are displayed for review, and are discarded on cancel, completion or quit. Python, Vosk and the operating system may retain freed memory or swap pages; this is not a secure-memory or forensic-erasure guarantee.

Persistent SQLite storage contains only validated preferences such as model path, microphone consent, time limits and theme. No transcript, audio, clipboard content, command payload, permission token or activity history belongs in the database. The application creates private configuration storage and can reset preferences. The model files themselves remain on disk until the user removes them.

## Desktop input

The RemoteDesktop portal requests keyboard control. The desktop presents its own permission dialog; the app checks the returned grant before allowing input. Permission is not restored from a saved token. No screen capture is requested. Desktop denial, revocation or session closure blocks future input. Emergency stop closes the session and cancels work. The app never uses raw input-device access, root, uinput or input-helper daemons.

The app uses PipeWire capture after its own explicit mic-consent step. This step is an application setting, not a claim that Linux exposes a universal microphone-consent portal. The operating system's own audio/device restrictions continue to apply.

Global shortcuts use the desktop portal and its consent UI. The app does not monitor arbitrary keys. Users may decline this permission and use the local controls.

## Confirmation and limits

Dictation and command modes are separate. Every action is reviewed and confirmed; commands capable of submission or destruction require another confirmation. Dictation cannot contain injected Enter/Tab or other control characters. Unknown commands are rejected. Confirmations expire and are single-use, and editing invalidates previous approval.

The portal cannot attest which application's field receives input. The user chooses the destination. App-specific keyboard behavior, clipboard contents, focus changes and partial failures remain relevant: this software does not claim that an approved action can never have unintended effects. A failed insertion must not be retried automatically.

This is an experimental community tool, not certified assistive technology. The GNOME compatibility test and accessibility testing with intended users are required before a stable support claim.
