#!/usr/bin/env python3
"""Exercise the real Plasma D-Bus QML bridge against GTK with fake live devices.

Run with PYTHONPATH=src .venv/bin/python scripts/check-widget-protocol.py.
Uses a private D-Bus, temporary XDG homes, Xvfb, and an offscreen Qt engine.
No host microphone, input, profile, or compositor is accessed.
"""

import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
SERVICE = "io.github.wayland_voice_control"


def service():
    import gi

    gi.require_version("Gtk", "4.0")
    from gi.repository import GLib

    from tests.test_controller import Audio, Remote, Scheduler
    from wayland_voice_control.app import create_application
    from wayland_voice_control.controller import Controller, PracticeInput

    scheduler = Scheduler()

    def factory(*, practice, store):
        return Controller(
            settings=store.load(),
            store=store,
            remote=PracticeInput() if practice else Remote(),
            audio=None if practice else Audio(),
            practice=practice,
            schedule=scheduler.schedule,
            dispatch=lambda f: f(),
            clock=lambda: scheduler.now,
        )

    app = create_application(background=True, controller_factory=factory)

    def helper(_connection, _sender, _path, _iface, method, _parameters, invocation):
        window = app.window
        if method == "Ready":
            window.practice_switch.set_active(False)
            window.model_path.set_text("/fake/private/model")
            window.mic_consent.set_active(True)
            window.persist_settings()
            window.controller.prepare_model()
            window.controller.connect()
            window.controller.remote.grant()
        elif method == "Complete":
            window.controller.audio.callbacks["on_result"]("private final transcript")
        elif method == "Crash":
            GLib.timeout_add(50, lambda: os._exit(0))
        elif method == "DisableActivation":
            Path(os.environ["WVC_WIDGET_TEST_SERVICE"]).unlink()
            subprocess.run(
                [
                    "dbus-send",
                    "--session",
                    "--type=method_call",
                    "--print-reply",
                    "--dest=org.freedesktop.DBus",
                    "/org/freedesktop/DBus",
                    "org.freedesktop.DBus.ReloadConfig",
                ],
                check=True,
                capture_output=True,
            )
        invocation.return_value(GLib.Variant("()", ()))

    def register_helper():
        from gi.repository import Gio

        interface = Gio.DBusNodeInfo.new_for_xml(
            '<node><interface name="io.github.wayland_voice_control.WidgetTest1">'
            + "".join(
                '<method name="' + name + '"/>'
                for name in ["Ready", "Complete", "Crash", "DisableActivation"]
            )
            + "</interface></node>"
        ).interfaces[0]
        app.get_dbus_connection().register_object(
            "/WidgetTest", interface, helper, None, None
        )
        return False

    GLib.idle_add(register_helper)
    raise SystemExit(app.run(["widget-protocol-test", "--background"]))


def check():
    with tempfile.TemporaryDirectory(prefix="wvc-widget-qml-") as directory:
        source = (ROOT / "tests/qml/widget-protocol.qml").read_text()
        ui = (ROOT / "integrations/plasma" / SERVICE / "contents/ui").as_uri()
        (Path(directory) / "tst_protocol.qml").write_text(
            source.replace("@WIDGET_UI@", ui)
        )
        runner = "/usr/lib/qt6/bin/qmltestrunner"
        if not Path(runner).exists():
            import shutil

            runner = shutil.which("qmltestrunner") or "qmltestrunner"
        raise SystemExit(subprocess.call([runner, "-input", directory, "-o", "-,txt"]))


if __name__ == "__main__":
    if "--service" in sys.argv:
        service()
    elif "--isolated-child" in sys.argv:
        check()
    else:
        with tempfile.TemporaryDirectory(prefix="wvc-widget-protocol-") as directory:
            base = Path(directory)
            config = base / "bus.conf"
            config.write_text(
                "<busconfig><type>session</type><listen>unix:tmpdir=/tmp</listen>"
                "<auth>EXTERNAL</auth><servicedir>"
                + escape(str(base / "data/dbus-1/services"))
                + '</servicedir><policy context="default">'
                '<allow send_destination="*"/><allow receive_sender="*"/>'
                '<allow own="*"/></policy></busconfig>'
            )
            runtime = base / "runtime"
            runtime.mkdir(mode=0o700)
            data = base / "data"
            services = data / "dbus-1/services"
            services.mkdir(parents=True)
            activation = services / (SERVICE + ".service")
            # Exercise D-Bus's actual activation parser with a hostile absolute path.
            launcher = base / 'launch space $dollar `tick` "quote" \\slash'
            launcher.write_text(
                "#!/bin/sh\nexec "
                + shlex.quote(sys.executable)
                + " "
                + shlex.quote(str(Path(__file__).resolve()))
                + " --service\n"
            )
            launcher.chmod(0o755)
            escaped = (
                str(launcher)
                .replace("\\", "\\\\")
                .replace('"', '\\"')
                .replace("$", "\\$")
                .replace("`", "\\`")
            )
            escaped = escaped.replace("\\", "\\\\")
            activation.write_text(
                "[D-BUS Service]\nName=" + SERVICE + '\nExec="' + escaped + '"\n'
            )
            env = dict(
                os.environ,
                XDG_DATA_HOME=str(data),
                XDG_CONFIG_HOME=str(base / "config"),
                XDG_CACHE_HOME=str(base / "cache"),
                XDG_RUNTIME_DIR=str(runtime),
                XDG_DATA_DIRS="/usr/local/share:/usr/share",
                QT_QPA_PLATFORM="offscreen",
                QT_QPA_PLATFORMTHEME="generic",
                QT_NO_XDG_DESKTOP_PORTAL="1",
                QT_QUICK_BACKEND="software",
                GDK_BACKEND="x11",
                GTK_A11Y="none",
                GSETTINGS_BACKEND="memory",
                WVC_WIDGET_TEST_COMMAND=str(base / "command"),
                WVC_WIDGET_TEST_SERVICE=str(activation),
                PYTHONPATH=os.pathsep.join([str(ROOT), str(ROOT / "src")]),
            )
            raise SystemExit(
                subprocess.call(
                    [
                        "dbus-run-session",
                        "--config-file=" + str(config),
                        "--",
                        "xvfb-run",
                        "-a",
                        sys.executable,
                        str(Path(__file__).resolve()),
                        "--isolated-child",
                    ],
                    env=env,
                )
            )
