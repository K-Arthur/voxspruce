# Background controls and KDE widget

The main window can be closed while the app stays available. Background operation
is explicit and session-only; it does not enable a wake word, open the microphone,
request permissions or change login startup.

## Background operation on GNOME or KDE

Open the app normally and enable **Keep available when window closes**. Complete
Live setup, model preparation and the desktop permission steps before recording.
Request global shortcuts to see the actual granted bindings, including **Show
controls**. The app-menu launcher and Show controls reopen the existing window.
Closing the window cancels recording and any pending review/countdown, then hides
it when background operation is enabled. Completed portal grants remain available
until Stop, settings changes, a switch of Practice/Live, permission revocation or
Quit. Ordinary closing without background operation exits as before.

A granted global push-to-talk shortcut can record while the window is hidden.
The finalized result opens the review window; the compositor decides whether to
focus it. Review and confirmation still happen through the main app. A panel
widget can also start and finish a bounded recording after the existing Live
setup gates pass. This recording is explicitly controlled from the widget, so
switching to another application's window does not cancel it. Close, Cancel,
Stop and the configured duration cap remain available.

Use **Quit** to stop everything and exit. **Stop** discards content and closes
both keyboard and global shortcut grants while leaving the app available to
reopen. There is no automatic reconnect or replay. In a fresh process, launching
`wayland-voice-control gui --background` starts a hidden resident Practice
instance; it is useful for explicit desktop activation. It never resumes Live
setup automatically. An explicit `--settings` instance has a separate bus
identity; the desktop widget controls only the default instance.

## KDE Plasma panel or desktop widget

The optional widget targets Plasma 6.7+ and its
`org.kde.plasma.workspace.dbus` QML module. GTK remains the application runtime;
the widget is a small native Plasma frontend. Older Plasma versions and GNOME
shell panel extensions are outside the tested widget target. GNOME users can
use the app-menu launcher and portal-based global shortcuts where supported.

From an installed checkout:

```sh
./scripts/install-local.sh
./scripts/install-widget.sh
```

The second script explicitly registers the widget and its D-Bus activation file
in the user's data directory. It does not add anything to the panel or desktop,
change login startup, restart Plasma or request elevated privileges. Use
Plasma's **Add Widgets** interface to add **Voxspruce** to a panel or
the desktop. The installer is also the update path after changing this checkout;
keep the checkout and its venv in place while using it.

Open the compact microphone control to see status and actions. **Open controls**
can start the app when it is not running. A cold start opens Practice, so complete
Live setup in the main app before Start recording becomes available. **Finish
and review** stops capture and opens the finalized result for review. **Cancel**
discards pending work; **Stop** also revokes grants. **Quit** exits the application.
The widget never displays transcript text, command phrases or private errors.

If activation fails, use the normal app-menu launcher, check that the installed
venv still exists, and rerun the widget installer. Mutating calls are never
retried automatically. Reopening the widget does not start the microphone.

To build a distributable widget archive:

```sh
.venv/bin/python scripts/build-widget.py
```

The archive is installed with Plasma's **Install Widget From Local File** option.
The matching activation service still needs the explicit local installer and a
working application executable. Installing the archive alone does not install
Python, GTK, models or application dependencies.

To remove, remove the widget from its panel/desktop, use
`kpackagetool6 --type Plasma/Applet --remove io.github.wayland_voice_control`, and
remove `$XDG_DATA_HOME/dbus-1/services/io.github.wayland_voice_control.service`
(default `~/.local/share/dbus-1/services/…`). Quit the running application
separately. This leaves preferences/models intact. The normal app-menu entry can
be removed independently as described in README.

## Voice control scope

The widget activates the app through buttons or a global shortcut. It does not
listen for a wake phrase while idle. Spoken built-in and custom phrases use the
existing explicitly started Commands recording and review workflow. Arbitrary
“click Save” control of other applications through AT-SPI is separate work and
is not provided by this widget.

## Local API and trust boundary

`io.github.wayland_voice_control.Controls1` is exported at
`/io/github/wayland_voice_control/Controls` on the application's session-bus name
`io.github.wayland_voice_control`. `GetStatus` returns `a{sv}` and
`StatusChanged(a{sv})` publishes updates. Version 1 status contains only `version`,
`practice`, `state`, `microphone`, `model`, `can_start`, `pending_review`,
`window_visible` and `background`. Only enumerations/booleans are included;
transcripts, drafts, paths, command details and free error/status strings are
excluded.

The zero-argument methods `Show`, `StartRecording`, `FinishRecording`, `Cancel`,
`Stop` and `Quit` return a boolean. Capture still requires saved Setup, Live,
explicit microphone consent, prepared local model, current keyboard grant and
an idle workflow. There is no method for confirming, submitting text/chords,
changing settings or granting permission. Calls run on GTK's main thread.

The session bus belongs to the logged-in user. Other applications already able
to access that bus can call these controls: the interface is not a security
boundary against malicious software running as the same user. Status and
controls are deliberately narrow; use Stop/Quit to revoke live capability.
