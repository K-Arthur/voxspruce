"""Keyboard-only portal sessions and fixed, single-use input execution.

All session changes/callbacks belong on the UI dispatcher. Input runs on a worker;
its cancellation Event is checked before each press, and releases run in finally.
No session, token, transcript, or permission is persisted.
"""

import threading
from typing import ClassVar
from uuid import uuid4

from .commands import COMMANDS, parse_key_chord
from .domain import ActionKind
from .transport import SESSION, PortalError

REMOTE = "org.freedesktop.portal.RemoteDesktop"
SHORTCUTS = "org.freedesktop.portal.GlobalShortcuts"
CHORDS = {
    identity: parse_key_chord(command.key_chord)[1]
    for identity, command in COMMANDS.items()
}


def keysym(character):
    code = ord(character)
    return code if code <= 0xFF else 0x01000000 | code


def background(callback):
    threading.Thread(target=callback, daemon=True).start()


class RemoteDesktop:
    def __init__(self, transport, *, dispatch, run_worker=background, on_closed=None):
        self.transport = transport
        self.dispatch = dispatch
        self.run_worker = run_worker
        self.on_closed = on_closed or (lambda: None)
        self.granted = False
        self._generation = 0
        self._session = None
        self._cancel_request = None
        self._closed_signal = None
        self._owner_signal = None
        self._input_cancel = threading.Event()
        self._busy = False

    def connect(self, callback, parent_window=""):
        self.close()
        generation = self._generation
        self._owner_signal = self.transport.subscribe_owner_lost(
            lambda: self._closed(generation)
        )

        def failed(message):
            if generation == self._generation:
                self.close()
                callback(False, PortalError(message))

        def request(method, signature, args, options, next_step):
            def response(code, results, error):
                if generation != self._generation:
                    if results.get("session_handle"):
                        self.transport.close_session(results["session_handle"])
                    return
                self._cancel_request = None
                if error or code != 0:
                    failed(
                        str(error)
                        if error
                        else "Keyboard permission was declined or unavailable."
                    )
                    return
                next_step(results)

            cancel = self.transport.request(
                REMOTE, method, signature, args, options, response
            )
            if generation == self._generation:
                self._cancel_request = cancel

        def created(results):
            session = results.get("session_handle")
            if not isinstance(session, str) or not session.startswith("/"):
                failed("Portal returned no valid session.")
                return
            self._session = session
            self._closed_signal = self.transport.subscribe(
                SESSION, "Closed", session, lambda *_: self._closed(generation)
            )
            request(
                "SelectDevices",
                "(oa{sv})",
                (session,),
                {"types": 1, "persist_mode": 0},
                selected,
            )

        def selected(_):
            request("Start", "(osa{sv})", (self._session, parent_window), {}, started)

        def started(results):
            devices = results.get("devices", 0)
            if not isinstance(devices, int) or not devices & 1:
                failed("The desktop did not grant keyboard control.")
                return
            self.granted = True
            callback(True, None)

        token = "wvc_" + uuid4().hex
        if hasattr(self.transport, "session_path"):
            self._session = self.transport.session_path(token)
        request(
            "CreateSession", "(a{sv})", (), {"session_handle_token": token}, created
        )

    def _closed(self, generation):
        if generation == self._generation:
            self.close()
            self.on_closed()

    def cancel_input(self):
        self._input_cancel.set()

    def close(self):
        self._generation += 1
        self.granted = False
        self.cancel_input()
        cancel, self._cancel_request = self._cancel_request, None
        if cancel:
            cancel()
        if self._owner_signal is not None:
            self.transport.unsubscribe(self._owner_signal)
            self._owner_signal = None
        if self._closed_signal is not None:
            self.transport.unsubscribe(self._closed_signal)
            self._closed_signal = None
        session, self._session = self._session, None
        if session:
            self.transport.close_session(session)

    def execute(self, action, callback):
        if not self.granted or self._session is None or self._busy:
            callback(PortalError("Keyboard access is unavailable or input is busy."))
            return
        session = self._session
        generation = self._generation
        cancel = self._input_cancel = threading.Event()
        self._busy = True

        def worker():
            error = None
            try:
                chords = (
                    [(keysym(char),) for char in action.payload]
                    if action.kind is ActionKind.TEXT
                    else [
                        parse_key_chord(
                            action.key_chord
                            if action.key_chord is not None
                            else COMMANDS[action.payload].key_chord
                        )[1]
                    ]
                )
                for chord in chords:
                    pressed = []
                    try:
                        for symbol in chord:
                            if cancel.is_set() or generation != self._generation:
                                raise PortalError(
                                    "Input cancelled; some text may already have been sent."
                                )
                            # A failing send may still have pressed the key remotely.
                            pressed.append(symbol)
                            self.transport.notify_key(session, symbol, 1)
                    finally:
                        release_error = None
                        for symbol in reversed(pressed):
                            try:
                                self.transport.notify_key(session, symbol, 0)
                            except Exception as caught:  # noqa: BLE001 - contain errors at the OS/model boundary
                                release_error = caught
                        if release_error:
                            raise release_error
            except Exception as caught:  # noqa: BLE001 - contain errors at the OS/model boundary
                error = caught
            finally:

                def complete():
                    self._busy = False
                    callback(error)

                self.dispatch(complete)

        self.run_worker(worker)


class GlobalShortcuts:
    """Only granted bindings emit events; confirm/cancel fire after key release."""

    PREFERRED: ClassVar = {
        "hold_to_talk": ("Hold to talk", "CTRL+ALT+space"),
        "confirm": ("Confirm reviewed action", "CTRL+ALT+Return"),
        "cancel": ("Cancel action", "CTRL+ALT+Escape"),
        "show_controls": ("Show controls", "CTRL+ALT+v"),
    }

    def __init__(self, transport, on_event, *, on_closed=None):
        self.transport = transport
        self.on_event = on_event
        self.on_closed = on_closed or (lambda: None)
        self.bindings = {}
        self._session = None
        self._signals = []
        self._pressed = set()
        self._generation = 0
        self._cancel_request = None

    def connect(self, callback, parent_window=""):
        self.close()
        generation = self._generation
        self._signals.append(
            self.transport.subscribe_owner_lost(lambda: self._closed(generation))
        )

        def response(next_step):
            def received(code, results, error):
                if generation != self._generation:
                    if results.get("session_handle"):
                        self.transport.close_session(results["session_handle"])
                    return
                self._cancel_request = None
                if error or code != 0:
                    self.close()
                    callback(
                        False,
                        error
                        or PortalError(
                            "Global shortcuts unavailable; use local controls."
                        ),
                    )
                    return
                next_step(results)

            return received

        def created(results):
            session = results.get("session_handle")
            if not isinstance(session, str) or not session.startswith("/"):
                self.close()
                callback(
                    False, PortalError("Global shortcuts returned no valid session.")
                )
                return
            self._session = session
            for signal in ("Activated", "Deactivated"):
                self._signals.append(
                    self.transport.subscribe(
                        SHORTCUTS,
                        signal,
                        None,
                        lambda values, name=signal: self._event(name, values),
                    )
                )
            self._signals.append(
                self.transport.subscribe(
                    SESSION, "Closed", session, lambda *_: self._closed(generation)
                )
            )
            bindings = [
                (key, {"description": value[0], "preferred_trigger": value[1]})
                for key, value in self.PREFERRED.items()
            ]
            self._cancel_request = self.transport.request(
                SHORTCUTS,
                "BindShortcuts",
                "(oa(sa{sv})sa{sv})",
                (session, bindings, parent_window),
                {},
                response(bound),
            )

        def bound(results):
            self.bindings = {
                key: details.get("trigger_description", "")
                for key, details in results.get("shortcuts", [])
                if key in self.PREFERRED
            }
            callback(True, None)

        token = "wvc_" + uuid4().hex
        if hasattr(self.transport, "session_path"):
            self._session = self.transport.session_path(token)
        self._cancel_request = self.transport.request(
            SHORTCUTS,
            "CreateSession",
            "(a{sv})",
            (),
            {"session_handle_token": token},
            response(created),
        )

    def _event(self, signal, values):
        session, key = values[:2]
        if session != self._session or key not in self.bindings:
            return
        if signal == "Activated" and key not in self._pressed:
            self._pressed.add(key)
            if key == "hold_to_talk":
                self.on_event(key, True)
        elif signal == "Deactivated" and key in self._pressed:
            self._pressed.remove(key)
            self.on_event(key, False)

    def _closed(self, generation):
        if generation == self._generation:
            self.close()
            self.on_closed()

    def close(self):
        self._generation += 1
        cancel, self._cancel_request = self._cancel_request, None
        if cancel:
            cancel()
        for token in self._signals:
            self.transport.unsubscribe(token)
        self._signals.clear()
        if self._session:
            self.transport.close_session(self._session)
        self._session = None
        self.bindings = {}
        self._pressed.clear()
