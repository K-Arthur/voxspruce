# Compatibility and release status

This is an experimental community tool. GNOME Wayland is the first intended
desktop target; a supported-desktop claim requires the recorded real-session
[kill test](manual-test.md). A passing test against a fake portal is not that test.

| Environment | Evidence collected | Status |
| --- | --- | --- |
| GNOME on Wayland | Standard keyboard portal implementation and protocol tests | Real permission UI, text insertion, Unicode/layouts and microphone workflow **not yet validated** |
| CachyOS / KDE Wayland development host | GTK4/libadwaita available; read-only portal discovery advertises keyboard and global shortcuts; local Vosk fixture decoding | Development environment only; **desktop input support not claimed** |
| Xvfb test display | Used for isolated native-widget verification | No real compositor, microphone or input compatibility evidence |
| Other KDE, Cinnamon, Sway, Hyprland and other compositors | No recorded run | Untested |
| X11 | No fallback input implementation | Not a supported control target; practice can run where GTK is available |
| Windows / macOS | Linux PipeWire/portal dependencies do not apply | Unsupported |

## Required runtime capabilities

Python 3.11 or newer, GTK4, libadwaita, PyGObject and Gio provide the native app.
Live speech additionally needs PipeWire's `pw-record`, the optional Vosk Python
package and an extracted local model. Live input needs a working session D-Bus,
RemoteDesktop portal keyboard capability and an explicit grant. GlobalShortcuts
is optional: local controls remain available when binding is unavailable or
declined. Local spoken read-back is optional and uses `espeak-ng` when installed.

Portal and model availability are shown separately from permission and actual
load success. No automatic fallback invokes raw device access, X11 input tools,
root helpers or cloud recognition. Obtain models and dependencies during setup;
normal recognition and review then run offline.

## Known practical limits

- Built-in command phrases are English. Custom phrases match exact case/whitespace
  normalized speech only; no fuzzy matching is performed. Recognition depends on
  the selected local model's language and vocabulary. Dictation quality also
  depends on that model.
- Custom chords use a bounded ASCII/named-key allowlist. Their application effects,
  modifier handling and keyboard layouts require real-session validation. Every
  custom shortcut requires two distinct confirmations. Scripts, text macros,
  key sequences and OS media keys are unsupported.
- A small speech model trades accuracy for size and speed. Live partial drafts
  can revise earlier words. Review the final text before approving it.
- The user chooses the target application and field. The portal cannot attest
  focus or identify a password field. Layout, Unicode and application keybinding
  differences require testing.
- Clipboard commands act on the system clipboard without inspecting it. An app
  may interpret pasted content or an approved key unexpectedly.
- An input failure can leave a partial insertion. The app reports failure and
  never automatically retries; inspect the destination before trying again.
- Capture offers both a held push-to-talk control and an explicit start/stop
  control. There is no wake word, always-listening mode or universal hands-free
  access claim.
- Automated GTK accessibility-backend tests cover selected roles, names, status
  announcements, headings and named groups. They do not establish AT-SPI transport,
  Orca speech/braille usability or accessibility standards compliance. Testing with
  intended voice-input users remains open; see [accessibility.md](accessibility.md).

See [validation.md](validation.md) for exact test evidence and
[performance.md](performance.md) for model/host-specific speech measurements.
