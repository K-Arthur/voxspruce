#!/usr/bin/env python3
"""Check the real AT-SPI wire using Practice, a private bus and Xvfb.

No host accessibility tree, microphone, portal grant or desktop input is used.
Only fixed synthetic test content is entered. This is not an Orca usability test.
"""

import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def stop(process):
    if process is not None and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)


def check():
    import gi

    gi.require_version("Atspi", "2.0")
    from gi.repository import Atspi, Gio, GLib

    Atspi.set_timeout(1000, 1000)
    # GTK 4.14 returns ARIA role names ("group", "text box", "status")
    # while newer GTK uses AT-SPI names. The protocol's enum IDs are stable.
    roles = {
        "button": (Atspi.Role.PUSH_BUTTON,),
        "heading": (Atspi.Role.HEADING,),
        # Ubuntu Noble backports GROUP -> PANEL for its older Orca. Native
        # GTK tests still require GROUP; the wire requires this exact named
        # section and its heading, with only these two supported mappings.
        "grouping": (Atspi.Role.GROUPING, Atspi.Role.PANEL),
        "check box": (Atspi.Role.CHECK_BOX,),
        "text": (Atspi.Role.TEXT,),
        "label": (Atspi.Role.LABEL,),
        "page tab": (Atspi.Role.PAGE_TAB,),
    }
    context = GLib.MainContext.default()

    def pump():
        # AT-SPI caches are updated by events; sleeping alone can read stale state.
        for _ in range(100):
            if not context.pending():
                break
            context.iteration(False)

    def wait(predicate, message, seconds=8):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            pump()
            try:
                value = predicate()
            except GLib.Error:
                # GTK may replace command rows while libatspi still holds their
                # old object paths. Retry the bounded lookup, never the action.
                value = None
            if value:
                return value
            time.sleep(0.02)
        raise AssertionError(message)

    registry = app = None
    try:
        # Start explicitly: some distributions' a11y launcher requires systemd.
        # Both GTK and libatspi use this private bus, never the host's a11y bus.
        registry_path = shutil.which("at-spi2-registryd")
        if registry_path is None:
            registry_path = next(
                (
                    str(path)
                    for path in (
                        Path("/usr/lib/at-spi2-registryd"),
                        Path("/usr/libexec/at-spi2-registryd"),
                        Path("/usr/lib/at-spi2-core/at-spi2-registryd"),
                    )
                    if path.is_file()
                ),
                None,
            )
        if registry_path is None:
            raise AssertionError("Install the distribution AT-SPI registry.")
        registry = subprocess.Popen(
            [registry_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)

        def registered():
            if registry.poll() is not None:
                raise AssertionError("Private AT-SPI registry exited.")
            return connection.call_sync(
                "org.freedesktop.DBus",
                "/org/freedesktop/DBus",
                "org.freedesktop.DBus",
                "NameHasOwner",
                GLib.Variant("(s)", ("org.a11y.atspi.Registry",)),
                GLib.VariantType.new("(b)"),
                Gio.DBusCallFlags.NONE,
                1000,
                None,
            ).unpack()[0]

        wait(registered, "Private AT-SPI registry did not register.")
        desktop = Atspi.get_desktop(0)
        if desktop is None:
            raise AssertionError("No private AT-SPI desktop.")
        with tempfile.TemporaryDirectory(prefix="wvc-a11y-settings-") as directory:
            app = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "wayland_voice_control",
                    "gui",
                    "--settings",
                    str(Path(directory) / "private/settings.db"),
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            def children(node):
                for index in range(node.get_child_count()):
                    child = node.get_child_at_index(index)
                    if child is not None:
                        yield child

            def walk(node, depth=0):
                if depth > 40:
                    raise AssertionError("Unexpected accessibility tree depth.")
                yield node
                for child in children(node):
                    yield from walk(child, depth + 1)

            def application():
                if app.poll() is not None:
                    raise AssertionError("Practice exited before accessibility checks.")
                return next(
                    (
                        child
                        for child in children(desktop)
                        if child.get_name() == "wayland-voice-control"
                    ),
                    None,
                )

            root = wait(application, "Practice not registered with AT-SPI.")

            def find(name, role):
                return next(
                    (
                        node
                        for node in walk(root)
                        if node.get_role() in roles[role] and node.get_name() == name
                    ),
                    None,
                )

            def require_node(name, role):
                try:
                    return wait(
                        lambda: find(name, role), "Missing named AT-SPI control."
                    )
                except AssertionError:
                    # Roles/counts only: never print editor values or transcripts.
                    from collections import Counter

                    matching_roles = []
                    counts = Counter()
                    for node in walk(root):
                        actual_role = node.get_role_name()
                        counts[actual_role] += 1
                        if node.get_name() == name:
                            matching_roles.append(actual_role)
                    raise AssertionError(
                        f"Missing AT-SPI role {role}; matching roles {matching_roles}; "
                        f"tree role counts {dict(counts)}"
                    ) from None

            def state(node, wanted):
                return node.get_state_set().contains(wanted)

            def activate(name, role="button"):
                node = require_node(name, role)
                if not state(node, Atspi.StateType.SENSITIVE):
                    raise AssertionError("Required accessibility action is disabled.")
                if not Atspi.Action.do_action(node, 0):
                    raise AssertionError("Accessibility action rejected.")

            def text_contents(node):
                # GTK 4.14's GtkEditable clamps end=-1 to zero. Request the
                # explicit complete character range on every supported version.
                count = Atspi.Text.get_character_count(node)
                return Atspi.Text.get_text(node, 0, count)

            def set_text(name, text):
                node = require_node(name, "text")
                if not Atspi.EditableText.set_text_contents(node, text):
                    raise AssertionError(
                        "Accessible editor rejected synthetic content."
                    )
                wait(
                    lambda: text_contents(node) == text,
                    "Accessible editor did not update.",
                )
                return node

            def status(starts):
                return next(
                    (
                        node
                        for node in walk(root)
                        if node.get_role() == Atspi.Role.STATUS_BAR
                        and text_contents(node).startswith(starts)
                    ),
                    None,
                )

            require_node("Voxspruce", "heading")
            for section in ("Speak, review, confirm", "Review the complete action"):
                require_node(section, "grouping")
                require_node(section, "heading")
            for name in ("Quit", "Stop", "Confirm reviewed action"):
                require_node(name, "button")
            require_node("Practice mode — simulate input only", "check box")
            hold = require_node("Hold to talk · Space while focused", "button")
            if state(hold, Atspi.StateType.SENSITIVE):
                raise AssertionError("Practice unexpectedly enables live capture.")

            set_text(
                "Typed practice example (up to 4000 characters)", "synthetic example"
            )
            activate("Review practice example")
            wait(lambda: status("Reviewing"), "Accessible review action did not run.")
            editor = require_node("Complete transcript editor", "text")
            wait(
                lambda: text_contents(editor) == "synthetic example",
                "Review does not expose complete synthetic text.",
            )
            if "synthetic example" in text_contents(status("Reviewing")):
                raise AssertionError("Private text leaked into status announcements.")
            activate("Edit transcript…")
            wait(lambda: status("Editing"), "Edit did not revoke review.")
            confirm = require_node("Confirm reviewed action", "button")
            wait(
                lambda: not state(confirm, Atspi.StateType.SENSITIVE),
                "Editing left confirmation enabled.",
            )
            set_text("Complete transcript editor", "corrected example")
            activate("Re-review complete edit")
            wait(lambda: status("Reviewing"), "Re-review did not restore review.")
            activate("Confirm reviewed action")
            require_node(
                "Practice output · simulated only:\nLiteral dictation · No Enter or Tab will be added.\ncorrected example",
                "label",
            )

            activate("Commands", "page tab")
            require_node("Custom voice shortcut", "heading")
            set_text("Voice phrase (1–120 characters)", "save synthetic document")
            set_text("One chord · e.g. Ctrl+S, Alt+F4, Shift+Tab", "Ctrl+S")
            activate("Save shortcut")
            activate("Practice “save synthetic document”")
            wait(lambda: status("Reviewing"), "Custom Practice review missing.")
            activate("Confirm reviewed action")
            wait(
                lambda: status("Awaiting second confirmation"),
                "Custom shortcut bypassed separate second approval.",
            )
            activate("Cancel · Escape")
            wait(lambda: status("Idle"), "Cancel did not clear review.")

            activate("Setup", "page tab")
            for name in (
                "Availability",
                "1 · Prepare an offline model",
                "2 · Explicit microphone consent",
                "3 · Desktop keyboard permission",
            ):
                require_node(name, "heading")
            consent = require_node(
                "I allow microphone capture after I explicitly start it", "check box"
            )
            if state(consent, Atspi.StateType.CHECKED):
                raise AssertionError(
                    "Fresh settings unexpectedly grant microphone consent."
                )
            require_node("Local Vosk model directory", "text")
            activate("Quit")
            wait(lambda: app.poll() == 0, "Accessible Quit did not exit cleanly.")
    finally:
        stop(app)
        Atspi.exit()
        stop(registry)
    print("AT-SPI Practice integration passed (no host input or microphone).")


def isolated():
    with tempfile.TemporaryDirectory(prefix="wvc-a11y-") as directory:
        base = Path(directory)
        config = base / "bus.conf"
        # No activation directories: no desktop portal, session manager or host
        # accessibility service is started by this test's private bus.
        config.write_text(
            "<busconfig><type>session</type><listen>unix:tmpdir=/tmp</listen>"
            '<auth>EXTERNAL</auth><policy context="default">'
            '<allow send_destination="*"/><allow receive_sender="*"/>'
            '<allow own="*"/></policy></busconfig>'
        )
        env = dict(os.environ)
        for key, name in (
            ("XDG_DATA_HOME", "data"),
            ("XDG_CONFIG_HOME", "config"),
            ("XDG_CACHE_HOME", "cache"),
            ("XDG_RUNTIME_DIR", "runtime"),
        ):
            path = base / name
            path.mkdir(mode=0o700)
            env[key] = str(path)
        env.update(
            GTK_A11Y="atspi",
            GDK_BACKEND="x11",
            GSK_RENDERER="cairo",
            GIO_USE_VFS="local",
            MESA_SHADER_CACHE_DISABLE="true",
            PYTHONPATH=str(ROOT / "src"),
            WVC_A11Y_PRIVATE_BUS="1",
        )
        # An inherited host a11y address must never reach the isolated child.
        env.pop("AT_SPI_BUS_ADDRESS", None)
        process = subprocess.Popen(
            [
                "dbus-run-session",
                "--config-file",
                str(config),
                "--",
                "xvfb-run",
                "-a",
                sys.executable,
                str(Path(__file__).resolve()),
                "--isolated-child",
            ],
            env=env,
            start_new_session=True,
        )
        try:
            return process.wait(timeout=60)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            print("AT-SPI integration timed out.", file=sys.stderr)
            return 1
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()


if __name__ == "__main__":
    if "--isolated-child" in sys.argv:
        if os.environ.get("WVC_A11Y_PRIVATE_BUS") != "1":
            raise SystemExit("Run this check without internal arguments.")
        os.environ["AT_SPI_BUS_ADDRESS"] = os.environ["DBUS_SESSION_BUS_ADDRESS"]
        check()
    else:
        raise SystemExit(isolated())
