"""Lazy native entry point and the single resident controller owner."""

import hashlib
import sys
from pathlib import Path

from .storage import SettingsError, SettingsStore

APPLICATION_ID = "io.github.wayland_voice_control"
CONTROLS_PATH = "/io/github/wayland_voice_control/Controls"
CONTROLS_INTERFACE = APPLICATION_ID + ".Controls1"


def application_identity(settings_path=None):
    """Explicit settings cannot redirect or replace the ordinary desktop instance."""
    if settings_path is None:
        return APPLICATION_ID, CONTROLS_PATH
    digest = hashlib.sha256(str(Path(settings_path).resolve()).encode()).hexdigest()[
        :24
    ]
    return APPLICATION_ID + ".settings_" + digest, CONTROLS_PATH + "_" + digest


def create_application(
    *, settings_path=None, background=False, controller_factory=None
):
    """Construct the native app without starting its loop or any live boundary."""
    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Adw, Gio, GLib

    from .domain import State
    from .ui_model import can_capture
    from .window import VoiceWindow

    application_id, controls_path = application_identity(settings_path)
    methods = "".join(
        f'<method name="{name}"><arg type="b" direction="out"/></method>'
        for name in (
            "Show",
            "StartRecording",
            "FinishRecording",
            "Cancel",
            "Stop",
            "Quit",
        )
    )
    interface = Gio.DBusNodeInfo.new_for_xml(
        f'<node><interface name="{CONTROLS_INTERFACE}">'
        '<method name="GetStatus"><arg type="a{sv}" direction="out"/></method>'
        + methods
        + '<signal name="StatusChanged"><arg type="a{sv}"/></signal></interface></node>'
    ).interfaces[0]

    class Application(Adw.Application):
        def __init__(self):
            super().__init__(
                application_id=application_id,
                flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE,
            )
            self.controls_path = controls_path
            self.window = None
            self.failed = False
            self._background = False
            self._quitting = False
            self._cleaned = False
            self._registration = None
            self._unsubscribe = None
            self._last_status = None

        def do_startup(self):
            Adw.Application.do_startup(self)
            try:
                kwargs = {"application": self, "store": SettingsStore(settings_path)}
                if controller_factory is not None:
                    kwargs["controller_factory"] = controller_factory
                self.window = VoiceWindow(**kwargs)
            except (SettingsError, OSError) as error:
                print(f"Cannot load private preferences: {error}", file=sys.stderr)
                self.failed = True
                self.quit()
                return
            self._registration = self.get_dbus_connection().register_object(
                controls_path, interface, self._method_call, None, None
            )
            self.window.keep_available.connect(
                "toggled", lambda toggle: self.set_background(toggle.get_active())
            )
            self.window.connect("notify::visible", lambda *_: self.publish_status())
            self.controller_changed()
            if background:
                self.set_background(True)

        def do_command_line(self, command_line):
            if self.failed:
                return 1
            if "--background" in command_line.get_arguments()[1:]:
                self.set_background(True)
            else:
                self.activate()
            return 0

        def do_activate(self):
            self.show_controls()

        def set_background(self, enabled):
            enabled = bool(enabled) and not self._quitting
            if enabled != self._background:
                self._background = enabled
                self.hold() if enabled else self.release()
            if self.window and self.window.keep_available.get_active() != enabled:
                self.window.keep_available.set_active(enabled)
            self.publish_status()
            if (
                not enabled
                and self.window
                and not self.window.get_visible()
                and not self._quitting
            ):
                self.show_controls()

        def show_controls(self):
            if self._quitting or not self.window:
                return False
            self.window.present()
            self.publish_status()
            return True

        def close_controls(self):
            if self._background and not self._quitting:
                self.window.cancel_action()
                self.window.set_visible(False)
                return True
            self.quit_controls()
            return False

        def controller_changed(self):
            if not self.window:
                return
            if self._unsubscribe:
                self._unsubscribe()
            self.window.controller.on_show_controls = self.show_controls
            self._unsubscribe = self.window.controller.subscribe(
                self._controller_updated
            )

        def _controller_updated(self, snapshot):
            if (
                snapshot.pending is not None
                and not self._quitting
                and not self.window.get_visible()
            ):
                self.window.stack.set_visible_child_name("voice")
                self.show_controls()
                self._notify_review(snapshot.pending.id)
            self.publish_status()

        def _notify_review(self, pending_id):
            def available(connection, result):
                try:
                    owned = connection.call_finish(result).unpack()[0]
                except GLib.Error:
                    return
                pending = self.window.controller.snapshot.pending
                if (
                    owned
                    and not self._quitting
                    and pending
                    and pending.id == pending_id
                    and not self.window.is_active()
                ):
                    notification = Gio.Notification.new("Voice action ready for review")
                    notification.set_body(
                        "Open Wayland Voice Control to review the action."
                    )
                    self.send_notification("review", notification)

            self.get_dbus_connection().call(
                "org.freedesktop.DBus",
                "/org/freedesktop/DBus",
                "org.freedesktop.DBus",
                "NameHasOwner",
                GLib.Variant("(s)", ("org.freedesktop.Notifications",)),
                GLib.VariantType.new("(b)"),
                Gio.DBusCallFlags.NO_AUTO_START,
                1000,
                None,
                available,
            )

        def get_status(self):
            snapshot = self.window.controller.snapshot
            microphone = snapshot.microphone_activity
            model = snapshot.model_readiness
            return {
                "version": GLib.Variant("u", 1),
                "practice": GLib.Variant("b", snapshot.practice),
                "state": GLib.Variant("s", snapshot.state.value),
                "microphone": GLib.Variant(
                    "s",
                    microphone
                    if microphone in {"idle", "loading", "recording", "processing"}
                    else "idle",
                ),
                "model": GLib.Variant(
                    "s",
                    model
                    if model in {"idle", "loading", "ready", "error"}
                    else "error",
                ),
                "can_start": GLib.Variant(
                    "b",
                    not self._quitting
                    and not self.window._settings_dirty
                    and can_capture(snapshot),
                ),
                "pending_review": GLib.Variant("b", snapshot.pending is not None),
                "window_visible": GLib.Variant("b", self.window.get_visible()),
                "background": GLib.Variant("b", self._background),
            }

        def publish_status(self):
            if not self.window or not self._registration or self._cleaned:
                return
            status = self.get_status()
            if status != self._last_status:
                self._last_status = status
                self.get_dbus_connection().emit_signal(
                    None,
                    controls_path,
                    CONTROLS_INTERFACE,
                    "StatusChanged",
                    GLib.Variant("(a{sv})", (status,)),
                )

        def start_recording(self):
            if (
                self._quitting
                or self.window._settings_dirty
                or not can_capture(self.window.controller.snapshot)
            ):
                return False
            self.set_background(True)
            self.window._stop_reader()
            return bool(self.window._safe(self.window.controller.start_recording))

        def finish_recording(self):
            if (
                self._quitting
                or self.window.controller.snapshot.state is not State.RECORDING
            ):
                return False
            self.window.controller.finish_recording()
            return True

        def quit_controls(self):
            if self._quitting:
                return True
            self._quitting = True
            if self.window:
                self.window.shutdown()
            self.set_background(False)
            self.quit()
            return True

        def _method_call(
            self,
            _connection,
            _sender,
            _path,
            _interface,
            method,
            parameters,
            invocation,
        ):
            if parameters.get_type_string() != "()":
                invocation.return_dbus_error(
                    "org.freedesktop.DBus.Error.InvalidArgs",
                    "This method accepts no arguments.",
                )
                return
            if method == "GetStatus":
                invocation.return_value(GLib.Variant("(a{sv})", (self.get_status(),)))
                return
            callbacks = {
                "Show": self.show_controls,
                "StartRecording": self.start_recording,
                "FinishRecording": self.finish_recording,
                "Cancel": lambda: self.window.cancel_action() or True,
                "Stop": lambda: self.window.stop_action() or True,
                "Quit": self.quit_controls,
            }
            invocation.return_value(GLib.Variant("(b)", (bool(callbacks[method]()),)))

        def do_shutdown(self):
            if self._cleaned:
                return
            self.quit_controls()
            self._cleaned = True
            if self._unsubscribe:
                self._unsubscribe()
                self._unsubscribe = None
            if self._registration:
                self.get_dbus_connection().unregister_object(self._registration)
                self._registration = None
            Adw.Application.do_shutdown(self)

    return Application()


def main(*, settings_path=None, background=False):
    try:
        import gi

        gi.require_version("Gtk", "4.0")
        gi.require_version("Adw", "1")
        from gi.repository import Gtk

        application = create_application(
            settings_path=settings_path, background=background
        )
    except (ImportError, ValueError):
        print(
            "Native GUI needs GTK4, libadwaita and PyGObject. Install the desktop packages in README.md; "
            "use a system-site-packages virtual environment. CLI doctor and commands still work.",
            file=sys.stderr,
        )
        return 1
    if not Gtk.init_check():
        print(
            "No GTK display available. Run inside a desktop session; doctor --json works headlessly.",
            file=sys.stderr,
        )
        return 1
    result = application.run(
        ["wayland-voice-control", *(["--background"] if background else [])]
    )
    return 1 if application.failed else result
