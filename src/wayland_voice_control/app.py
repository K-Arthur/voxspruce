"""Lazy native entry point, with actionable recovery for missing desktop packages."""

import sys

from .storage import SettingsError, SettingsStore


def main(*, settings_path=None):
    try:
        import gi

        gi.require_version("Gtk", "4.0")
        gi.require_version("Adw", "1")
        from gi.repository import Adw, Gio, Gtk

        from .window import VoiceWindow
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

    class Application(Adw.Application):
        def __init__(self):
            super().__init__(
                application_id="io.github.wayland_voice_control",
                flags=Gio.ApplicationFlags.NON_UNIQUE,
            )
            self.window = None
            self.failed = False

        def do_activate(self):
            if self.window is None:
                try:
                    self.window = VoiceWindow(
                        application=self, store=SettingsStore(settings_path)
                    )
                except (SettingsError, OSError) as error:
                    print(f"Cannot load private preferences: {error}", file=sys.stderr)
                    self.failed = True
                    self.quit()
                    return
            self.window.present()

        def do_shutdown(self):
            if self.window:
                self.window.shutdown()
            Adw.Application.do_shutdown(self)

    application = Application()
    result = application.run([])
    return 1 if application.failed else result
