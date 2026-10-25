"""Read-only capability checks: no CreateSession, capture, storage writes or input."""

import importlib.util
import os
import shutil
import sqlite3
from contextlib import closing
from pathlib import Path

from .storage import Settings, SettingsError, SettingsStore, default_settings_path
from .transport import DESKTOP, DESTINATION


def read_settings(path):
    path = Path(path)
    if not path.exists():
        return Settings()
    if path.is_symlink() or path.parent.is_symlink():
        raise SettingsError("Settings path cannot be a symbolic link.")
    with closing(
        sqlite3.connect(path.absolute().as_uri() + "?mode=ro", uri=True)
    ) as connection:
        connection.row_factory = sqlite3.Row
        SettingsStore._check_version(connection)
        return SettingsStore._read(connection)


def probe_dependencies():
    result = {
        "gi": False,
        "gtk4": False,
        "adwaita": False,
        "vosk": importlib.util.find_spec("vosk") is not None,
    }
    try:
        import gi

        result["gi"] = True
        gi.require_version("Gtk", "4.0")
        result["gtk4"] = True
        gi.require_version("Adw", "1")
        result["adwaita"] = True
    except (ImportError, ValueError):
        pass
    return result


def probe_portals():
    """Introspection and read-only properties never present a permission dialog."""
    from gi.repository import Gio, GLib

    connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    xml = connection.call_sync(
        DESTINATION,
        DESKTOP,
        "org.freedesktop.DBus.Introspectable",
        "Introspect",
        None,
        GLib.VariantType("(s)"),
        Gio.DBusCallFlags.NONE,
        3000,
        None,
    ).unpack()[0]
    interfaces = {
        interface.name for interface in Gio.DBusNodeInfo.new_for_xml(xml).interfaces
    }
    remote = "org.freedesktop.portal.RemoteDesktop"
    result = {
        "remote_desktop": remote in interfaces,
        "global_shortcuts": "org.freedesktop.portal.GlobalShortcuts" in interfaces,
        "keyboard": False,
    }
    if result["remote_desktop"]:
        try:
            devices = connection.call_sync(
                DESTINATION,
                DESKTOP,
                "org.freedesktop.DBus.Properties",
                "Get",
                GLib.Variant("(ss)", (remote, "AvailableDeviceTypes")),
                GLib.VariantType("(v)"),
                Gio.DBusCallFlags.NONE,
                3000,
                None,
            ).unpack()[0]
            result["keyboard"] = bool(devices & 1)
        except GLib.Error as error:
            result["error"] = str(error)
    return result


def diagnose(
    *,
    environment=None,
    settings_path=None,
    which=shutil.which,
    dependency_probe=probe_dependencies,
    portal_probe=probe_portals,
):
    environment = os.environ if environment is None else environment
    report = {
        "session_type": environment.get("XDG_SESSION_TYPE", "unknown"),
        "desktop": environment.get("XDG_CURRENT_DESKTOP", "unknown"),
        "pw_record": which("pw-record"),
        "dependencies": dependency_probe(),
    }
    try:
        settings = read_settings(settings_path or default_settings_path(environment))
    except (SettingsError, sqlite3.Error, OSError) as error:
        settings = Settings()
        report["settings_error"] = str(error)
    report["model_path"] = settings.model_path
    report["model_exists"] = bool(
        settings.model_path and Path(settings.model_path).expanduser().is_dir()
    )
    try:
        report["portal"] = portal_probe()
    except Exception as error:  # noqa: BLE001 - capability probes must report unavailable dependencies
        report["portal"] = {
            "remote_desktop": False,
            "global_shortcuts": False,
            "keyboard": False,
            "error": str(error),
        }
    report["note"] = (
        "Availability is not permission or a compatibility test. "
        "No microphone or desktop-input request was made."
    )
    return report
