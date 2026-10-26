"""Portal request protocol independent of Gio and real desktop permissions.

The boundary wire uses async calls/signals and an injected timeout scheduler.
Response subscriptions precede method calls because portals may respond first.
"""

from uuid import uuid4

DESTINATION = "org.freedesktop.portal.Desktop"
DESKTOP = "/org/freedesktop/portal/desktop"
REQUEST = "org.freedesktop.portal.Request"
SESSION = "org.freedesktop.portal.Session"


class PortalError(RuntimeError):
    """A portal request failed, expired, or was cancelled."""


class RequestTransport:
    def __init__(self, wire, *, token_factory=None, timeout=60):
        self.wire = wire
        self._token = token_factory or (lambda: "wvc_" + uuid4().hex)
        self.timeout = timeout

    def request(self, interface, method, signature, args, options, callback):
        token = self._token()
        if not token or any(
            not (c.isascii() and (c.isalnum() or c == "_")) for c in token
        ):
            raise ValueError("Invalid portal request token.")
        sender = self.wire.unique_name.lstrip(":").replace(".", "_")
        path = f"{DESKTOP}/request/{sender}/{token}"
        finished = False
        verified = False
        early_response = None
        subscription = None
        owner_subscription = None
        cancel_timer = None

        def close_request():
            self.wire.call(REQUEST, "Close", path, "()", (), lambda *_: None)

        def finish(code, results, error):
            nonlocal finished
            if finished:
                return
            finished = True
            if subscription is not None:
                self.wire.unsubscribe(subscription)
            if owner_subscription is not None:
                self.wire.unsubscribe(owner_subscription)
            if cancel_timer:
                cancel_timer()
            callback(code, results, error)

        def response(values):
            nonlocal early_response
            if finished:
                return
            if verified:
                finish(values[0], values[1], None)
            else:
                early_response = values

        def returned(values, error):
            nonlocal verified
            if error:
                finish(2, {}, error)
            elif not values or values[0] != path:
                if values and isinstance(values[0], str):
                    self.wire.call(
                        REQUEST, "Close", values[0], "()", (), lambda *_: None
                    )
                close_request()
                finish(
                    2, {}, PortalError("Portal returned an unexpected request handle.")
                )
            elif finished:
                close_request()
            else:
                verified = True
                if early_response is not None:
                    finish(early_response[0], early_response[1], None)

        def cancel(message="Portal request cancelled."):
            if not finished:
                close_request()
                finish(2, {}, PortalError(message))

        subscription = self.wire.subscribe(REQUEST, "Response", path, response)
        owner_subscription = self.wire.subscribe_owner_lost(
            lambda: finish(2, {}, PortalError("Desktop portal service ended."))
        )
        cancel_timer = self.wire.schedule(
            self.timeout, lambda: cancel("Portal request timed out.")
        )
        try:
            self.wire.call(
                interface,
                method,
                DESKTOP,
                signature,
                (*args, {**options, "handle_token": token}),
                returned,
            )
        except Exception as error:  # noqa: BLE001 - adapter failures must cancel safely
            finish(2, {}, error)
        return cancel

    def session_path(self, token):
        sender = self.wire.unique_name.lstrip(":").replace(".", "_")
        return f"{DESKTOP}/session/{sender}/{token}"

    def close_session(self, path):
        self.wire.call(SESSION, "Close", path, "()", (), lambda *_: None)

    def subscribe(self, *args):
        return self.wire.subscribe(*args)

    def subscribe_owner_lost(self, callback):
        return self.wire.subscribe_owner_lost(callback)

    def unsubscribe(self, token):
        self.wire.unsubscribe(token)

    def notify_key(self, session, symbol, state):
        self.wire.notify_key(session, symbol, state)
