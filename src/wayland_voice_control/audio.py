"""In-memory local Vosk recognition with bounded PipeWire stdout reads.

The worker owns recognizer/content. Only the model is cached. stop() releases a
hold and finalizes current audio; cancel() invalidates every queued callback.
A watchdog terminates capture even if an OS read stalls. No shell/audio files.
"""

import math
import select
import subprocess
import threading
import time
from pathlib import Path

from .portal import background
from .speech import DecoderError, StreamingDecoder


class AudioError(RuntimeError):
    """Local recognition or microphone capture could not complete."""


class _CaptureFault(AudioError):
    """Only fixed, application-authored messages may cross the worker boundary."""


def load_local_model(path):
    import vosk

    # Vosk filters native severities against this threshold; -1 still logs errors.
    # Below assertion (-3), error (-2), warning (-1), and informational (0).
    vosk.SetLogLevel(-4)
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
        clock=time.monotonic,
    ):
        self.dispatch = dispatch
        self.run_worker = run_worker
        self.load_model = load_model
        self.make_recognizer = make_recognizer
        self.spawn = spawn
        self.read_chunk = read_chunk
        self.timer_factory = timer_factory
        self.clock = clock
        self._pending_draft = ""
        self._lock = threading.RLock()
        self._generation = 0
        self._active = False
        self._stop = threading.Event()
        self._process = None
        self._model = None
        self._model_path = None

    @staticmethod
    def _local_path(model_path):
        if (
            not model_path
            or "://" in str(model_path)
            or not Path(model_path).expanduser().is_dir()
        ):
            raise AudioError("Choose an existing local Vosk model directory.")
        return Path(model_path).expanduser().resolve()

    def _emit(self, generation, callback, value):
        def deliver():
            if generation == self._generation:
                callback(value)

        self.dispatch(deliver)

    def _load(self, path):
        # Only the single excluded worker accesses the model cache.
        if self._model is None or self._model_path != path:
            self._model, self._model_path = self.load_model(path), path

    def prepare(self, model_path, *, on_state, on_error):
        """Load/cache a local model off-thread, without any microphone permission."""
        path = self._local_path(model_path)
        with self._lock:
            if self._active:
                return False
            self._active = True
            self._generation += 1
            generation = self._generation
        self._emit(generation, on_state, "loading")

        def worker():
            error = None
            try:
                self._load(path)
            except Exception:  # noqa: BLE001 - dependency messages may contain private data
                error = AudioError(
                    "Local model preparation failed. Check the model directory."
                )
            finally:
                with self._lock:
                    self._active = False
            self._emit(generation, on_state, "error" if error else "ready")
            if error:
                self._emit(generation, on_error, error)

        self.run_worker(worker)
        return True

    def start(
        self,
        model_path,
        *,
        consent,
        limit,
        on_activity,
        on_result,
        on_error,
        on_draft=None,
    ):
        if consent is not True:
            raise AudioError("Enable microphone consent before recording.")
        path = self._local_path(model_path)
        if (
            isinstance(limit, bool)
            or not isinstance(limit, (int, float))
            or not math.isfinite(limit)
            or not 5 <= limit <= 60
        ):
            raise AudioError("Capture duration must be between 5 and 60 seconds.")
        with self._lock:
            if self._active:
                return False
            self._active = True
            self._generation += 1
            generation = self._generation
            stop = self._stop = threading.Event()

        def emit(callback, value):
            self._emit(generation, callback, value)

        draft_queued = False
        last_draft = float("-inf")

        def draft(text):
            nonlocal draft_queued, last_draft
            if on_draft is None:
                return
            with self._lock:
                if generation != self._generation or stop.is_set():
                    return
                self._pending_draft = text
                if draft_queued or self.clock() - last_draft < 0.2:
                    return
                draft_queued = True
                last_draft = self.clock()

            def deliver():
                nonlocal draft_queued, last_draft
                with self._lock:
                    draft_queued = False
                    if generation != self._generation or stop.is_set():
                        return
                    last_draft = self.clock()
                    text = self._pending_draft
                    self._pending_draft = ""
                on_draft(text)

            self.dispatch(deliver)

        emit(on_activity, "loading")

        def worker():
            process = timer = recognizer = None
            decoder = None
            text = ""
            error = None
            released_before_capture = False
            try:
                self._load(path)
                # The same lock protects release and spawn: releasing during load
                # must never cause a later microphone process to be opened.
                with self._lock:
                    if generation != self._generation or stop.is_set():
                        released_before_capture = True
                    else:
                        recognizer = self.make_recognizer(self._model)
                        decoder = StreamingDecoder(recognizer)
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
                            raise _CaptureFault(
                                "The microphone recorder exited unexpectedly."
                            )
                        if len(chunk) > 4096:
                            raise _CaptureFault(
                                "The microphone returned an oversized audio block."
                            )
                        draft(decoder.accept(chunk))
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
                            raise _CaptureFault(
                                "The microphone returned an oversized audio block."
                            )
                        draft(decoder.accept(chunk))
                    emit(on_activity, "processing")
                    text = decoder.finish()
            except (_CaptureFault, DecoderError) as caught:
                error = AudioError(str(caught))
            except Exception:  # noqa: BLE001 - dependency messages may contain private speech
                error = AudioError(
                    "Local recognition failed. Check the local model and microphone, "
                    "then try a new recording."
                )
            finally:
                with self._lock:
                    stop.set()
                    self._pending_draft = ""
                cleanup_failed = False
                if timer:
                    try:
                        timer.cancel()
                    except Exception:  # noqa: BLE001 - never expose dependency exception payloads
                        cleanup_failed = True
                if process:
                    try:
                        _cleanup(process)
                    except Exception:  # noqa: BLE001 - never expose process exception payloads
                        cleanup_failed = True
                if cleanup_failed:
                    error = AudioError(
                        "Microphone cleanup failed. Stop the application and check "
                        "the local audio service before recording again."
                    )
                with self._lock:
                    self._active = False
                    self._process = None
                    self._pending_draft = ""
                if decoder:
                    decoder.clear()
                recognizer = None
                emit(on_activity, "idle")
                if error:
                    emit(on_error, error)
                else:
                    emit(on_result, text)

        self.run_worker(worker)
        return True

    def _release(self, generation):
        with self._lock:
            if generation != self._generation:
                return
            self._stop.set()
            self._pending_draft = ""
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
