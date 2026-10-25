# Wayland Voice Control

A native GTK4/libadwaita Linux app for offline, held voice input: speak, review
the complete result, then explicitly confirm dictation or one exact command.
MIT licensed. Starts in **Practice**, which uses typed examples and simulated
output; it constructs no microphone, desktop portal or live input adapter.

GNOME Wayland is the intended first control target. The native app and automated
protocol/widget tests are implemented. Real GNOME consent/input, microphone
latency and testing with intended voice-input users remain release gates;
this is experimental community software, not certified assistive technology.

## Install and run

Use Python 3.11+ and the distribution's GTK bindings. For Debian 12+/Ubuntu 24.04+:

```sh
sudo apt install python3-venv python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1 pipewire-bin xdg-desktop-portal xdg-desktop-portal-gnome
```

For Arch/GNOME:

```sh
sudo pacman -S python python-pip python-gobject gtk4 libadwaita pipewire xdg-desktop-portal xdg-desktop-portal-gnome
```

Use the portal backend appropriate to the desktop actually running. Installing
GNOME's backend on another compositor does not establish compatibility. The
[official PyGObject instructions](https://pygobject.gnome.org/getting_started.html)
cover the GTK binding packages. Optional local spoken read-back needs `espeak-ng`.

From this checkout, install the Python package and an application-menu launcher:

```sh
./scripts/install-local.sh
./scripts/run-local.sh
```

The script creates `.venv` with system packages, installs `.[speech]` with pip,
and copies a desktop entry/icon under `$XDG_DATA_HOME` (default `~/.local/share`).
It uses the network only for dependency installation; it never downloads a model
or changes system packages. Remove those two launcher/icon files to uninstall
the application-menu entry; remove the checkout/venv separately when wanted.

For Practice only, or without creating a desktop launcher:

```sh
python3 -m venv --system-site-packages .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m wayland_voice_control
# Install the local speech engine when wanted:
.venv/bin/python -m pip install -e '.[speech]'
```

## First live session

1. Explore Voice and Commands in Practice. Type a literal example, review, edit,
   re-review, confirm and inspect the clearly labeled simulated output. Commands
   require Commands mode; the words `press enter` in Dictation remain literal.
2. Obtain and extract a model from the [official Vosk catalogue](https://alphacephei.com/vosk/models).
   `vosk-model-small-en-us-0.15` is the initial English candidate. Select the
   extracted directory containing the model files, rather than its ZIP or parent.
   The built-in command phrases are English. Model licenses are separate.
3. In Voice, turn off Practice. In Setup, choose the local model directory with
   the native folder chooser or enter a path, choose microphone consent explicitly
   (default off), and Save. Any Setup edit immediately pauses live input, revokes
   runtime microphone consent and closes live grants. Unsaved changes block
   preparation/reconnection/global bindings until Save. Save still requires
   explicit preparation and reconnecting.
4. Click **Prepare saved model** and wait for **ready**. This loads locally without
   opening the mic. Idle/loading/error cannot start live capture, including through
   global shortcuts. A typical small model needs about 300 MB of runtime memory;
   larger models can require much more, according to the Vosk catalogue.
5. Click **Request desktop keyboard access** and approve the desktop's keyboard
   dialog. Capability availability and a saved preference do not constitute a
   grant. Optionally request global shortcuts and read the actual returned bindings.
6. Choose Dictation or Commands, then hold the talk button (or Space while it has
   focus, or an approved global shortcut). A provisional draft appears while held;
   it is never approved or sent. Release to finish and review the final result.
7. Check the literal text or the exact phrase/chord/description/risk. **Edit
   transcript** revokes approval before the editor becomes editable. **Re-review**
   creates a fresh action. Confirm once; every high-risk/custom action needs the
   separately labeled second confirmation. Select a disposable destination during
   the visible local countdown. The portal cannot verify the intended field.

Stop remains in the titlebar; Escape cancels. Stop, changing Practice/Live,
settings changes and exit close live sessions. The microphone stops on release,
cancel, focus loss of the local hold control or the duration cap. Cancel discards
content; reconnecting never replays it. An input failure may leave partial text;
it is reported and never automatically retried.

## Commands and custom shortcuts

| Exact phrase | One chord | Risk |
| --- | --- | --- |
| next field | Tab | Normal |
| previous field | Shift+Tab | Normal |
| copy | Ctrl+C | Normal |
| paste | Ctrl+V | Normal |
| undo | Ctrl+Z | Normal |
| select all | Ctrl+A | Normal |
| press enter | Return | High |
| close window | Alt+F4 | High |
| delete selection | Delete | High |

The Commands view searches the catalogue and offers Practice buttons. Create,
edit, disable or delete a custom phrase mapped to one validated chord, e.g.
`save document` → `Ctrl+S`. Preview shows the exact normalized mapping. All custom
shortcuts are high risk because effects depend on the destination app; each needs
two confirmations. Built-ins cannot be replaced. At most 100 entries, with
120-character phrases, 64-character chord input and 240-character descriptions.
See the [complete allowed keys and configuration contract](docs/adapter-api.md).

## Privacy, diagnostics and limits

No runtime network calls, cloud recognition, account, telemetry, audio files,
automatic model downloads or transcript history. Only preferences and intentional
custom configuration are saved. Drafts/final text stay in memory; model loading is
cached, capture is duration-bounded, and release drains at most 64 KiB of queued
PCM. Dictation/drafts are bounded to 4000 characters. Freed memory/swap are not
securely erased. See [privacy.md](docs/privacy.md) for those boundaries.

```sh
.venv/bin/python -m wayland_voice_control --help
.venv/bin/python -m wayland_voice_control doctor --json
.venv/bin/python -m wayland_voice_control commands
.venv/bin/python -m wayland_voice_control gui --settings /path/to/private/settings.db
```

`doctor` is read-only and does not create settings or ask for consent. It reports
capability availability, not actual compositor compatibility or granted access.
Missing GTK gives an actionable CLI error. Missing Vosk/model/recorder is explained
in Setup or preparation/capture status; Practice needs none of them. Optional
read-back uses `espeak-ng --stdin` only and stops when the reviewed action changes.
There is no wake word, always-listening mode, raw-device or privileged input fallback.
Unicode, keyboard layouts and destination behavior require real-session testing.

## Design and evidence

- [Architecture and state flow](docs/architecture.md), [controller API](docs/adapter-api.md)
- [SQL/JSON configuration schemas](docs/schema.md), [privacy](docs/privacy.md)
- [Performance measurements](docs/performance.md), [validation evidence](docs/validation.md)
- [Compatibility limits](docs/compatibility.md), [GNOME manual kill test](docs/manual-test.md)
- [Development, CI and distribution](docs/development.md)
- [Source-linked research](docs/research.md), [Vibe data-availability report](docs/vibe-data-availability.md)
- [Implementation plan](docs/superpowers/plans/2026-10-25-wayland-voice-control.md)
