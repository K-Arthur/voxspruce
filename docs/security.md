# Security and safe initialization

## Startup and first-run sequence

1. `doctor` reports local capabilities without creating preferences or requesting
   desktop access. The GUI checks GTK/display availability before opening the
   private settings store.
2. The first GUI session opens in Practice. Practice constructs no microphone,
   portal or live-input adapters. A second launch activates the existing
   application instance, avoiding duplicate capture/shortcut sessions.
3. Live setup is deliberately staged: choose a local model, prepare it without
   microphone capture, save microphone consent (off by default), and request
   keyboard/global-shortcut access through desktop portals. A saved preference
   never restores a desktop grant.
4. Live capture is user-activated, limited to the configured duration, streamed
   to the local recognizer and not written to disk. Drafts are provisional.
   Input requires reviewing the final result and explicit confirmation; higher
   risk actions need a second confirmation.

The app does not install a background service, autostart listener, wake word,
cloud fallback, telemetry, or automatic model downloader. Offline use does not
mean setup has no network: Python dependencies and model files are obtained
separately by the user.

## Stored data and local permissions

Settings are stored in an application-specific directory with mode `0700` and a
SQLite database with mode `0600`. The application rejects symlink settings
paths and refuses a shared settings directory instead of silently changing its
permissions. The database stores preferences and intentional custom shortcut
configuration only; it has no transcript, audio, history or permission-token
tables. Reset removes custom shortcuts and restores microphone consent to off.

Audio and reviewed text are transient process data. Cancel and shutdown clear
workflow state, but Python/native allocators, operating-system swap and crash
dumps are outside the app's control. This is not secure-memory erasure. See
[privacy.md](privacy.md) for data-flow details.

## Trust boundaries and remaining risks

- The selected model directory is local, but its files are parsed by native
  Vosk/Kaldi code in the app process. Use a model from a source you trust. Model
  preparation has no microphone permission, but it is not a sandbox and no
  strict memory or wall-clock budget is enforced around native model loading.
- PipeWire, GTK, portals, Vosk/Kaldi and optional espeak-ng run with the user's
  account privileges. Their vulnerabilities are not contained by this app.
- Desktop consent authorizes a capability; it does not prove which window or
  field has focus. A confirmed key chord can therefore affect an unexpected
  destination if focus changes. The app cannot verify the receiving app.
- The optional `espeak-ng` process receives only the reviewed action through
  stdin. Capture and speech subprocesses use fixed argument arrays, no shell,
  bounded lifetimes and sanitized app-authored errors. Python documents that
  avoiding implicit shell invocation prevents shell metacharacters from being
  interpreted as shell syntax ([subprocess security considerations](https://docs.python.org/3/library/subprocess.html#security-considerations)).
- GitHub CI declares `contents: read`, disables checkout credential persistence
  and pins actions to full commit SHAs. Dependabot proposes workflow and Python
  dependency updates; those updates still require review and successful tests.
  GitHub recommends minimum token permissions and immutable action references
  ([secure use reference](https://docs.github.com/en/actions/reference/security/secure-use)).

This is experimental assistive software, not a security-certified product.
Security review does not establish compositor compatibility, screen-reader
quality, speech accuracy or safety for every user and destination application.
