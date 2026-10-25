import tempfile
import unittest

from wayland_voice_control.audio import AudioCapture, AudioError


class Process:
    def __init__(self):
        self.terminated = self.killed = self.waited = False
        self.stdout = self

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True

    def wait(self, timeout=None):
        self.waited = True
        return 0

    def close(self):
        pass


class Recognizer:
    def __init__(self):
        self.chunks = []

    def AcceptWaveform(self, chunk):
        self.chunks.append(chunk)
        return len(self.chunks) == 1

    def Result(self):
        return '{"text": "hello"}'

    def PartialResult(self):
        return '{"partial": ""}'

    def FinalResult(self):
        return '{"text": "world"}'


class Timer:
    def __init__(self, seconds, callback):
        self.callback = callback
        self.cancelled = False

    def start(self):
        pass

    def cancel(self):
        self.cancelled = True


class AudioTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.jobs, self.callbacks, self.events, self.results, self.errors = (
            [],
            [],
            [],
            [],
            [],
        )
        self.process = Process()
        self.recognizer = Recognizer()
        self.spawned = []
        self.timers = []
        self.capture = AudioCapture(
            dispatch=self.callbacks.append,
            run_worker=self.jobs.append,
            load_model=lambda path: object(),
            make_recognizer=lambda model: self.recognizer,
            spawn=self.spawn,
            read_chunk=self.read,
            timer_factory=self.timer,
        )
        self.reads = 0

    def spawn(self):
        self.spawned.append(True)
        return self.process

    def timer(self, limit, callback):
        timer = Timer(limit, callback)
        self.timers.append(timer)
        return timer

    def read(self, process, timeout):
        self.reads += 1
        if self.reads == 2:
            self.capture.stop()
        return b"\0\0"

    def start(self, **kwargs):
        return self.capture.start(
            self.directory.name,
            consent=True,
            limit=5,
            on_activity=self.events.append,
            on_result=self.results.append,
            on_error=self.errors.append,
            **kwargs,
        )

    def flush(self):
        while self.callbacks:
            self.callbacks.pop(0)()

    def test_explicit_consent_and_local_existing_model_required(self):
        with self.assertRaises(AudioError):
            self.capture.start(
                self.directory.name,
                consent=False,
                limit=5,
                on_activity=lambda _: None,
                on_result=lambda _: None,
                on_error=lambda _: None,
            )
        with self.assertRaises(AudioError):
            self.capture.start(
                "/does/not/exist",
                consent=True,
                limit=5,
                on_activity=lambda _: None,
                on_result=lambda _: None,
                on_error=lambda _: None,
            )
        self.assertFalse(self.jobs)

    def test_release_while_loading_never_spawns_microphone(self):
        self.start()
        self.assertFalse(self.start())
        self.capture.stop()
        self.jobs.pop()()
        self.flush()
        self.assertFalse(self.spawned)
        self.assertEqual(self.results, [""])
        self.assertNotIn("recording", self.events)

    def test_segments_final_result_cleanup_and_callbacks_dispatched(self):
        self.start()
        self.jobs.pop()()
        self.assertEqual(self.results, [])
        self.flush()
        self.assertEqual(self.results, ["hello world"])
        self.assertEqual(self.events, ["loading", "recording", "processing", "idle"])
        self.assertTrue(self.process.terminated)
        self.assertTrue(self.process.waited)
        self.assertTrue(self.timers[0].cancelled)

    def test_unexpected_eof_is_error(self):
        self.capture.read_chunk = lambda *_: b""
        self.start()
        self.jobs.pop()()
        self.flush()
        self.assertEqual(self.results, [])
        self.assertIn("unexpectedly", str(self.errors[0]))
        self.assertTrue(self.process.waited)

    def test_silence_returns_empty_not_an_invented_transcript(self):
        self.recognizer.AcceptWaveform = lambda chunk: False
        self.recognizer.FinalResult = lambda: '{"text": ""}'
        self.start()
        self.jobs.pop()()
        self.flush()
        self.assertEqual(self.results, [""])

    def test_cancel_drops_queued_content_and_late_callbacks(self):
        self.start()
        self.jobs.pop()()
        self.capture.cancel()
        self.flush()
        self.assertEqual(self.results, [])
        self.assertEqual(self.events, [])

    def test_duration_cap_stops_child_and_finishes(self):
        def read(*_):
            self.timers[0].callback()

        self.capture.read_chunk = read
        self.start()
        self.jobs.pop()()
        self.flush()
        self.assertTrue(self.process.terminated)
        self.assertEqual(self.results, ["world"])

    def test_model_failure_does_not_spawn_and_is_dispatched(self):
        def fail(_):
            raise RuntimeError("bad model")

        self.capture.load_model = fail
        self.start()
        self.jobs.pop()()
        self.flush()
        self.assertEqual(self.spawned, [])
        self.assertIn("Check the local model and microphone", str(self.errors[0]))

    def test_model_is_cached_recognizer_is_fresh_each_session(self):
        models, recognizers = [], []
        self.capture.load_model = lambda path: models.append(path) or object()
        self.capture.make_recognizer = lambda model: (
            recognizers.append(model) or self.recognizer
        )
        for _ in range(2):
            self.reads = 0
            self.start()
            self.jobs.pop()()
            self.flush()
        self.assertEqual(len(models), 1)
        self.assertEqual(len(recognizers), 2)

    def test_cancel_excludes_new_worker_until_old_capture_cleanup_finishes(self):
        self.start()
        self.capture.cancel()
        self.assertFalse(self.start())
        self.jobs.pop()()
        self.assertTrue(self.start())

    def test_child_timeout_escalates_to_kill(self):
        import subprocess

        calls = []

        def wait(timeout=None):
            calls.append(timeout)
            if len(calls) == 1:
                raise subprocess.TimeoutExpired("pw-record", timeout)
            return 0

        self.process.wait = wait
        self.start()
        self.jobs.pop()()
        self.flush()
        self.assertTrue(self.process.killed)
        self.assertEqual(calls, [1, 1])

    def test_release_drains_bounded_queued_pcm_before_final_result(self):
        chunks = iter([b"\x01\x01", b"\x02\x02", b""])

        def read(*_):
            chunk = next(chunks)
            if chunk == b"\x01\x01":
                self.capture.stop()
            return chunk

        self.capture.read_chunk = read
        self.start()
        self.jobs.pop()()
        self.flush()
        self.assertEqual(self.recognizer.chunks, [b"\x01\x01", b"\x02\x02"])
        self.assertEqual(self.results, ["hello world"])

    def test_stop_unblocks_a_waiting_capture_reader_and_reaps_child(self):
        import threading

        from wayland_voice_control.portal import background

        entered, released, finished = (
            threading.Event(),
            threading.Event(),
            threading.Event(),
        )
        self.capture.run_worker = background
        original_terminate = self.process.terminate

        def terminate():
            original_terminate()
            released.set()

        self.process.terminate = terminate

        def read(*_):
            entered.set()
            if not released.wait(1):
                raise RuntimeError("blocked reader was not stopped")
            return b""

        self.capture.read_chunk = read
        original_wait = self.process.wait

        def wait(timeout=None):
            result = original_wait(timeout)
            finished.set()
            return result

        self.process.wait = wait
        self.start()
        self.assertTrue(entered.wait(1))
        self.capture.stop()
        self.assertTrue(finished.wait(1))
        self.assertTrue(self.process.terminated)
        self.assertTrue(self.process.waited)

    def test_release_inside_model_load_never_starts_recorder(self):
        def load(_):
            self.capture.stop()
            return object()

        self.capture.load_model = load
        self.start()
        self.jobs.pop()()
        self.flush()
        self.assertFalse(self.spawned)
        self.assertNotIn("recording", self.events)

    def test_dependency_exception_payload_never_reaches_callback_or_output(self):
        import contextlib
        import io

        sentinel = "recognized private text: example confidential note"
        for exception_type in (ValueError, AudioError):
            with self.subTest(exception_type=exception_type):
                self.errors.clear()
                self.reads = 0

                def fail(_chunk, exception_type=exception_type):
                    raise exception_type(sentinel)

                self.recognizer.AcceptWaveform = fail
                output = io.StringIO()
                with (
                    contextlib.redirect_stdout(output),
                    contextlib.redirect_stderr(output),
                ):
                    self.start()
                    self.jobs.pop()()
                    self.flush()
                self.assertEqual(len(self.errors), 1)
                self.assertNotIn(sentinel, str(self.errors[0]))
                self.assertNotIn(sentinel, repr(self.errors[0]))
                self.assertIsNone(self.errors[0].__context__)
                self.assertEqual(output.getvalue(), "")
                self.assertIn(
                    "Check the local model and microphone", str(self.errors[0])
                )

    def test_cleanup_exception_payload_never_reaches_callback(self):
        sentinel = "recognized private text: example confidential note"

        def fail(timeout=None):
            raise ValueError(sentinel)

        self.process.wait = fail
        self.start()
        self.jobs.pop()()
        self.flush()
        self.assertEqual(len(self.errors), 1)
        self.assertNotIn(sentinel, str(self.errors[0]))
        self.assertIn("Microphone cleanup failed", str(self.errors[0]))
        self.assertIsNone(self.errors[0].__context__)

    def test_timer_cleanup_exception_is_private_and_does_not_skip_child_cleanup(self):
        sentinel = "recognized private text: example confidential note"

        def timer(limit, callback):
            result = Timer(limit, callback)

            def fail():
                raise ValueError(sentinel)

            result.cancel = fail
            return result

        self.capture.timer_factory = timer
        self.start()
        self.jobs.pop()()
        self.flush()
        self.assertTrue(self.process.waited)
        self.assertEqual(len(self.errors), 1)
        self.assertNotIn(sentinel, str(self.errors[0]))
        self.assertIn("Microphone cleanup failed", str(self.errors[0]))

    def test_drafts_are_coalesced_throttled_and_cleared_at_finish(self):
        self.assertIn(
            "on_draft", __import__("inspect").signature(self.capture.start).parameters
        )
        now = [0.0]
        drafts = []
        self.capture.clock = lambda: now[0]
        self.recognizer.AcceptWaveform = lambda chunk: False
        self.recognizer.PartialResult = lambda: '{"partial":"draft"}'

        def read(*_):
            self.reads += 1
            now[0] += 0.05
            if self.reads == 1:
                self.flush()
            if self.reads == 2:
                self.flush()
                self.assertEqual(drafts, ["draft"])
            if self.reads == 8:
                self.assertLessEqual(len(self.callbacks), 1)
                self.flush()
                self.assertEqual(drafts, ["draft", "draft"])
            if self.reads == 100:
                self.assertLessEqual(len(self.callbacks), 1)
                self.capture.stop()
                return b""
            return b"\0\0"

        self.capture.read_chunk = read
        self.start(on_draft=drafts.append)
        self.jobs.pop()()
        self.flush()
        self.assertEqual(drafts, ["draft", "draft"])
        self.assertEqual(self.results, ["world"])
        self.assertEqual(self.capture._pending_draft, "")

    def test_cancel_clears_queued_draft_and_dependency_errors_stay_private(self):
        self.assertIn(
            "on_draft", __import__("inspect").signature(self.capture.start).parameters
        )
        drafts = []
        self.recognizer.AcceptWaveform = lambda chunk: False
        self.recognizer.PartialResult = lambda: '{"partial":22}'
        self.start(on_draft=drafts.append)
        self.jobs.pop()()
        self.flush()
        self.assertEqual(drafts, [])
        self.assertIn("invalid text", str(self.errors[-1]))
        self.errors.clear()
        self.recognizer.PartialResult = lambda: '{"partial":"private draft"}'
        self.reads = 0
        self.start(on_draft=drafts.append)
        self.jobs.pop()()
        self.capture.cancel()
        self.flush()
        self.assertEqual(drafts, [])
        self.assertEqual(self.capture._pending_draft, "")

    def test_prepare_uses_worker_caches_model_and_never_opens_microphone(self):
        self.assertTrue(hasattr(self.capture, "prepare"))
        states, models = [], []
        self.capture.load_model = lambda path: models.append(path) or object()
        self.assertTrue(
            self.capture.prepare(
                self.directory.name, on_state=states.append, on_error=self.errors.append
            )
        )
        self.assertEqual(models, [])
        self.assertFalse(self.start())
        self.flush()
        self.assertEqual(states, ["loading"])
        self.jobs.pop()()
        self.flush()
        self.assertEqual(states, ["loading", "ready"])
        self.assertEqual(self.spawned, [])
        self.start()
        self.jobs.pop()()
        self.flush()
        self.assertEqual(len(models), 1)

    def test_prepare_cancellation_suppresses_queued_and_load_racing_readiness(self):
        self.assertTrue(hasattr(self.capture, "prepare"))
        for cancel_during_load in (False, True):
            states = []

            def load(_, cancel_during_load=cancel_during_load):
                if cancel_during_load:
                    self.capture.cancel()
                return object()

            self.capture._model = None
            self.capture.load_model = load
            self.capture.prepare(
                self.directory.name, on_state=states.append, on_error=self.errors.append
            )
            self.jobs.pop()()
            self.capture.cancel()
            self.flush()
            self.assertEqual(states, [])
            self.assertEqual(self.spawned, [])

    def test_prepare_failure_is_sanitized_and_does_not_poison_new_request(self):
        self.assertTrue(hasattr(self.capture, "prepare"))
        states = []

        def load(_):
            raise RuntimeError("private dependency contents")

        self.capture.load_model = load
        self.capture.prepare(
            self.directory.name, on_state=states.append, on_error=self.errors.append
        )
        self.jobs.pop()()
        self.flush()
        self.assertEqual(states, ["loading", "error"])
        self.assertNotIn("private", str(self.errors[0]))
        self.capture.load_model = lambda _: object()
        self.assertTrue(
            self.capture.prepare(
                self.directory.name, on_state=states.append, on_error=self.errors.append
            )
        )

    def test_prepare_cancel_during_real_worker_load_keeps_exclusion_until_completion(
        self,
    ):
        self.assertTrue(hasattr(self.capture, "prepare"))
        import threading

        from wayland_voice_control.portal import background

        entered, released, finished = (
            threading.Event(),
            threading.Event(),
            threading.Event(),
        )
        states = []

        def load(_):
            entered.set()
            if not released.wait(1):
                raise RuntimeError("test load blocked")
            return object()

        def worker(job):
            def run():
                try:
                    job()
                finally:
                    finished.set()

            background(run)

        self.capture.load_model = load
        self.capture.run_worker = worker
        self.capture.prepare(
            self.directory.name, on_state=states.append, on_error=self.errors.append
        )
        self.assertTrue(entered.wait(1))
        self.capture.cancel()
        self.assertFalse(self.start())
        released.set()
        self.assertTrue(finished.wait(1))
        self.flush()
        self.assertEqual(states, [])
        self.assertEqual(self.spawned, [])

    def test_failed_capture_discards_pending_draft_without_empty_late_callback(self):
        drafts = []
        self.recognizer.AcceptWaveform = lambda _: False
        self.recognizer.PartialResult = lambda: '{"partial":"private draft"}'

        def read(*_):
            self.reads += 1
            if self.reads == 2:
                raise RuntimeError("capture fault")
            return b"\0\0"

        self.capture.read_chunk = read
        self.start(on_draft=drafts.append)
        self.jobs.pop()()
        self.flush()
        self.assertEqual(drafts, [])
        self.assertEqual(len(self.errors), 1)

    def test_resuming_stalled_dispatch_does_not_burst_draft_updates(self):
        now, drafts = [0.0], []
        self.capture.clock = lambda: now[0]
        self.recognizer.AcceptWaveform = lambda _: False
        self.recognizer.PartialResult = lambda: '{"partial":"draft"}'

        def read(*_):
            self.reads += 1
            if self.reads == 2:
                now[0] = 0.9
                self.flush()
            if self.reads == 3:
                now[0] = 0.91
                self.flush()
                self.capture.stop()
                return b""
            return b"\0\0"

        self.capture.read_chunk = read
        self.start(on_draft=lambda text: drafts.append((now[0], text)))
        self.jobs.pop()()
        self.flush()
        self.assertEqual(drafts, [(0.9, "draft")])
