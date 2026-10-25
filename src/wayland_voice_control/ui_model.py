"""Presentation rules and explicitly separated controller construction.

This module imports no GTK and constructs no live boundary for Practice.
"""

from .controller import Controller, PracticeInput
from .domain import ActionKind, State
from .storage import Settings


def can_capture(snapshot):
    return (
        not snapshot.practice
        and snapshot.microphone_consent
        and snapshot.permission_granted
        and snapshot.model_readiness == "ready"
        and snapshot.state is State.IDLE
    )


def action_details(action):
    if action is None:
        return "No action awaiting review."
    if action.kind is ActionKind.TEXT:
        return "Literal dictation · No Enter or Tab will be added.\n" + action.payload
    return (
        f"Exact phrase: {action.phrase}\nExact chord: {action.key_chord}\n"
        f"Description: {action.description or 'No description supplied.'}\n"
        f"{'Custom · ' if action.custom else ''}"
        f"{'High risk · requires two separate confirmations' if action.risk.value == 'high' else 'Normal risk · requires confirmation'}"
    )


def create_controller(*, practice, store=None):
    from .gio_transport import dispatch, schedule

    settings = store.load() if store is not None else Settings()
    if practice:
        return Controller(
            settings=settings,
            store=store,
            remote=PracticeInput(),
            audio=None,
            dispatch=dispatch,
            schedule=schedule,
            practice=True,
        )
    # Only the explicitly selected Live mode constructs OS adapters.
    from .audio import AudioCapture
    from .gio_transport import GioWire
    from .portal import GlobalShortcuts, RemoteDesktop
    from .transport import RequestTransport

    transport = RequestTransport(GioWire())
    return Controller(
        settings=settings,
        store=store,
        remote=RemoteDesktop(transport, dispatch=dispatch),
        audio=AudioCapture(dispatch=dispatch),
        dispatch=dispatch,
        schedule=schedule,
        shortcuts=GlobalShortcuts(transport, lambda *_: None),
    )


def dependency_status():
    """Read-only local presence checks; no imports of recognizers or live adapters."""
    import importlib.util
    import shutil

    return "\n".join(
        (
            "Vosk: installed."
            if importlib.util.find_spec("vosk")
            else "Vosk: missing — install the Python speech extra: pip install -e '.[speech]' in this app's environment.",
            "pw-record: available."
            if shutil.which("pw-record")
            else "pw-record: missing — install PipeWire recorder tools (pipewire-bin on Debian/Ubuntu; pipewire on Arch).",
            "espeak-ng: available (optional read-back)."
            if shutil.which("espeak-ng")
            else "espeak-ng: missing (optional) — install espeak-ng only if local read-back is wanted.",
            "Presence is not model readiness, portal capability or granted permission. Practice needs none of these dependencies.",
        )
    )
