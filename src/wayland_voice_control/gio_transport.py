"""Lazy Gio boundary; construction never requests consent or opens a microphone."""

from .transport import DESTINATION


def dispatch(callback):
    from gi.repository import GLib

    def once():
        callback()
        return GLib.SOURCE_REMOVE

    GLib.idle_add(once)


def schedule(seconds, callback):
    from gi.repository import GLib

    source = None

    def once():
        nonlocal source
        source = None
        callback()
        return GLib.SOURCE_REMOVE

    source = GLib.timeout_add(max(1, int(seconds * 1000)), once)

    def cancel():
        nonlocal source
        if source is not None:
            GLib.source_remove(source)
            source = None

    return cancel


def _typed(value):
    from gi.repository import GLib

    if isinstance(value, dict):
        return {
            key: GLib.Variant("u" if type(item) is int else "s", item)
            for key, item in value.items()
        }
    if isinstance(value, (tuple, list)):
        return tuple(_typed(item) for item in value)
    return value


class GioWire:
    def __init__(self, connection=None):
        from gi.repository import Gio

        self.connection = connection or Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self.unique_name = self.connection.get_unique_name()

    def call(self, interface, method, path, signature, args, callback):
        from gi.repository import Gio, GLib

        def done(connection, result, *_):
            try:
                value = connection.call_finish(result).unpack()
            except GLib.Error as error:
                callback(None, error)
            else:
                callback(value, None)

        self.connection.call(
            DESTINATION,
            path,
            interface,
            method,
            GLib.Variant(signature, _typed(args)),
            None,
            (
                Gio.DBusCallFlags.NO_AUTO_START
                if method == "Close"
                else Gio.DBusCallFlags.NONE
            ),
            60000,
            None,
            done,
        )

    def subscribe(self, interface, signal, path, callback):
        from gi.repository import Gio

        return self.connection.signal_subscribe(
            DESTINATION,
            interface,
            signal,
            path,
            None,
            Gio.DBusSignalFlags.NONE,
            lambda _connection, _sender, _path, _interface, _signal, values, *_: (
                callback(values.unpack())
            ),
        )

    def subscribe_owner_lost(self, callback):
        """Watch only the portal name; initial lazy activation is not a loss."""
        from gi.repository import Gio

        def changed(_connection, _sender, _path, _interface, _signal, values, *_):
            name, before, after = values.unpack()
            if name == DESTINATION and before and before != after:
                callback()

        return self.connection.signal_subscribe(
            "org.freedesktop.DBus",
            "org.freedesktop.DBus",
            "NameOwnerChanged",
            "/org/freedesktop/DBus",
            DESTINATION,
            Gio.DBusSignalFlags.NONE,
            changed,
        )

    def unsubscribe(self, token):
        self.connection.signal_unsubscribe(token)

    def schedule(self, seconds, callback):
        return schedule(seconds, callback)

    def notify_key(self, session, symbol, state):
        from gi.repository import Gio, GLib

        self.connection.call_sync(
            DESTINATION,
            "/org/freedesktop/portal/desktop",
            "org.freedesktop.portal.RemoteDesktop",
            "NotifyKeyboardKeysym",
            GLib.Variant("(oa{sv}iu)", (session, {}, symbol, state)),
            None,
            Gio.DBusCallFlags.NO_AUTO_START,
            5000,
            None,
        )
