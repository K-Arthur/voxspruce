"""In-memory local Vosk recognition with bounded PipeWire stdout reads.

The worker owns recognizer/content. Only the model is cached. stop() releases a
hold and finalizes current audio; cancel() invalidates every queued callback.
A watchdog terminates capture even if an OS read stalls. No shell/audio files.
"""

import json
import math
import select
import subprocess
import threading
from pathlib import Path

from .portal import background


class AudioError(RuntimeError):
    """Local recognition or microphone capture could not complete."""


def load_local_model(path):
    import vosk

    vosk.SetLogLevel(-1)
    return vosk.Model(str(path))


def make_recognizer(model):
    import vosk

    return vosk.KaldiRecognizer(model, 16000)


def spawn_recorder():
    return subprocess.Popen(
        ["pw-record", "--rate=16000", "--channels=1", "--format=s16", "--raw", "-"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        shell=False,
        bufsize=0,
    )


def read_chunk(process, timeout):
    ready, _, _ = select.select([process.stdout], [], [], timeout)
    return process.stdout.read(4096) if ready else None


def _cleanup(process):
    """Termination plus bounded waits; a blocked capture never holds the UI."""
    try:
        process.terminate()
    except (ProcessLookupError, OSError):
        pass
    try:
        process.wait(timeout=1)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=1)
    finally:
        if process.stdout:
            process.stdout.close()


class AudioCapture:
    def __init__(
        self,
        *,
        dispatch,
        run_worker=background,
        load_model=load_local_model,
        make_recognizer=make_recognizer,
        spawn=spawn_recorder,
        read_chunk=read_chunk,
        timer_factory=threading.Timer,
    ):
        self.dispatch = dispatch
        self.run_worker = run_worker
        self.load_model = load_model
        self.make_recognizer = make_recognizer
        self.spawn = spawn
        self.read_chunk = read_chunk
        self.timer_factory = timer_factory
        self._lock = threading.RLock()
        self._generation = 0
        self._active = False
        self._stop = threading.Event()
        self._process = None
        self._model = None
        self._model_path = None

    def start(self, model_path, *, consent, limit, on_activity, on_result, on_error):
        if consent is not True:
            raise AudioError("Enable microphone consent before recording.")
        if (
            not model_path
            or "://" in str(model_path)
            or not Path(model_path).expanduser().is_dir()
        ):
            raise AudioError("Choose an existing local Vosk model directory.")
        if (
            isinstance(limit, bool)
            or not isinstance(limit, (int, float))
            or not math.isfinite(limit)
            or not 5 <= limit <= 60
        ):
            raise AudioError("Capture duration must be between 5 and 60 seconds.")
        path = Path(model_path).expanduser().resolve()
        with self._lock:
            if self._active:
                return False
            self._active = True
            self._generation += 1
            generation = self._generation
            stop = self._stop = threading.Event()

        def emit(callback, value):
            def deliver():
                if generation == self._generation:
                    callback(value)

            self.dispatch(deliver)

        emit(on_activity, "loading")

        def worker():
            process = timer = recognizer = None
            segments = []
            total_characters = 0
            error = None
            released_before_capture = False

            def collect(raw):
                nonlocal total_characters
                text = json.loads(raw).get("text", "")
                if not isinstance(text, str):
                    raise AudioError("The recognizer returned invalid text.")
                total_characters += len(text) + 1
                if total_characters > 4001:
                    raise AudioError(
                        "Recognized text exceeded the 4000 character limit."
                    )
                if text.strip():
                    segments.append(text.strip())

            try:
                if self._model is None or self._model_path != path:
                    model = self.load_model(path)
                    with self._lock:
                        self._model, self._model_path = model, path
                # The same lock protects release and spawn: releasing during load
                # must never cause a later microphone process to be opened.
                with self._lock:
                    if generation != self._generation or stop.is_set():
                        released_before_capture = True
                    else:
                        recognizer = self.make_recognizer(self._model)
                        process = self._process = self.spawn()
                if not released_before_capture:
                    emit(on_activity, "recording")
                    timer = self.timer_factory(limit, lambda: self._release(generation))
                    timer.daemon = True
                    timer.start()
                    while not stop.is_set():
                        chunk = self.read_chunk(process, 0.1)
                        if chunk is None:
                            continue
                        if not chunk:
                            if stop.is_set():
                                break
                            raise AudioError(
                                "The microphone recorder exited unexpectedly."
                            )
                        if len(chunk) > 4096:
                            raise AudioError(
                                "The microphone returned an oversized audio block."
                            )
                        if recognizer.AcceptWaveform(chunk):
                            collect(recognizer.Result())
                    # After normal release the terminated recorder may still have
                    # PCM queued in its pipe. Drain at most 64 KiB without waiting;
                    # cancellation discards content rather than prolonging capture.
                    for _ in range(16):
                        if generation != self._generation:
                            break
                        chunk = self.read_chunk(process, 0)
                        if not chunk:
                            break
                        if len(chunk) > 4096:
                            raise AudioError(
                                "The microphone returned an oversized audio block."
                            )
                        if recognizer.AcceptWaveform(chunk):
                            collect(recognizer.Result())
                    emit(on_activity, "processing")
                    collect(recognizer.FinalResult())
            except Exception as caught:  # noqa: BLE001 - contain errors at the OS/model boundary
                error = AudioError(f"Local recognition failed: {caught}")
            finally:
                if timer:
                    timer.cancel()
                if process:
                    try:
                        _cleanup(process)
                    except Exception as caught:  # noqa: BLE001 - contain errors at the OS/model boundary
                        error = AudioError(f"Microphone cleanup failed: {caught}")
                with self._lock:
                    self._active = False
                    self._process = None
                recognizer = None
                emit(on_activity, "idle")
                if error:
                    emit(on_error, error)
                else:
                    emit(on_result, " ".join(segments))
                segments.clear()

        self.run_worker(worker)
        return True

    def _release(self, generation):
        with self._lock:
            if generation != self._generation:
                return
            self._stop.set()
            if self._process:
                try:
                    self._process.terminate()
                except (ProcessLookupError, OSError):
                    pass

    def stop(self):
        self._release(self._generation)

    def cancel(self):
        with self._lock:
            self._release(self._generation)
            self._generation += 1
            # Keep exclusion until the old worker has cleaned up its child.
            # Queued callbacks are invalidated immediately.
