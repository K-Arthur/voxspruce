import io
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import Mock


class BenchmarkTests(unittest.TestCase):
    def module(self):
        from wayland_voice_control import speech_benchmark

        self.assertTrue(hasattr(speech_benchmark, "benchmark"))
        return speech_benchmark

    def wav(self, frames=4096, rate=16000, channels=1, width=2):
        output = io.BytesIO()
        with wave.open(output, "wb") as stream:
            stream.setparams((channels, width, rate, 0, "NONE", "not compressed"))
            stream.writeframes(b"\0" * frames * channels * width)
        output.seek(0)
        return output

    def test_shared_decoder_chunk_boundaries_and_measured_statistics(self):
        module = self.module()
        recognizer = Mock()
        recognizer.AcceptWaveform.side_effect = [True, False]
        recognizer.Result.return_value = '{"text":"secret one"}'
        recognizer.PartialResult.return_value = '{"partial":"secret draft"}'
        recognizer.FinalResult.return_value = '{"text":"secret final"}'
        times = iter([0, 0.5, 1, 1.01, 2, 2.03, 3, 3.02])
        with tempfile.TemporaryDirectory() as model:
            report = module.benchmark(
                self.wav(),
                model,
                clock=lambda: next(times),
                load_model=lambda _: object(),
                make_recognizer=lambda _, recognizer=recognizer: recognizer,
            )
        self.assertEqual(
            [len(call.args[0]) for call in recognizer.AcceptWaveform.call_args_list],
            [4096, 4096],
        )
        self.assertAlmostEqual(report["cold_load_seconds"], 0.5)
        self.assertAlmostEqual(report["audio_seconds"], 0.256)
        self.assertAlmostEqual(report["decode_seconds"], 0.06)
        self.assertAlmostEqual(report["realtime_factor"], 0.06 / 0.256)
        self.assertAlmostEqual(report["chunk_p50_seconds"], 0.01)
        self.assertAlmostEqual(report["chunk_p95_seconds"], 0.03)
        self.assertAlmostEqual(report["chunk_max_seconds"], 0.03)
        self.assertAlmostEqual(report["finalization_seconds"], 0.02)
        self.assertEqual(report["partial_count"], 1)
        self.assertNotIn("secret", str(report))

    def test_invalid_wav_formats_and_duration_rejected_before_model_load(self):
        module = self.module()
        for arguments in (
            {"rate": 8000},
            {"channels": 2},
            {"width": 1},
            {"frames": 0},
            {"frames": 960001},
        ):
            with (
                self.subTest(arguments=arguments),
                tempfile.TemporaryDirectory() as model,
            ):
                load = Mock()
                with self.assertRaises(module.BenchmarkError):
                    module.benchmark(self.wav(**arguments), model, load_model=load)
                load.assert_not_called()

    def test_truncated_audio_and_private_decoder_exceptions_have_fixed_errors(self):
        module = self.module()
        for stream in (io.BytesIO(self.wav().getvalue()[:-2]), self.wav()):
            recognizer = Mock()
            recognizer.AcceptWaveform.side_effect = ValueError("private transcript")
            with tempfile.TemporaryDirectory() as model:
                with self.assertRaises(module.BenchmarkError) as caught:
                    module.benchmark(
                        stream,
                        Path(model),
                        load_model=lambda _: object(),
                        make_recognizer=lambda _, recognizer=recognizer: recognizer,
                    )
                self.assertNotIn("private", str(caught.exception))
                self.assertIsNone(caught.exception.__cause__)

    def test_paced_replay_measures_compute_time_separately_from_arrival_lag(self):
        module = self.module()
        self.assertIn(
            "paced", __import__("inspect").signature(module.benchmark).parameters
        )
        now, waits = [0.0], []
        recognizer = Mock()

        def accept(_):
            now[0] += 0.2
            return False

        def wait(seconds):
            waits.append(seconds)
            now[0] += seconds

        recognizer.AcceptWaveform.side_effect = accept
        recognizer.PartialResult.return_value = '{"partial":""}'
        recognizer.FinalResult.return_value = '{"text":""}'
        with tempfile.TemporaryDirectory() as model:
            report = module.benchmark(
                self.wav(),
                model,
                paced=True,
                clock=lambda: now[0],
                sleep=wait,
                load_model=lambda _: object(),
                make_recognizer=lambda _: recognizer,
            )
        self.assertEqual(waits, [0.128])
        self.assertAlmostEqual(report["decode_seconds"], 0.4)
        # Second chunk arrived at .256; finish at .528 includes accumulated backlog.
        self.assertAlmostEqual(report["max_replay_lag_seconds"], 0.272)

    def test_truncated_wav_rejects_missing_pcm_after_decoding_available_blocks(self):
        module = self.module()
        recognizer = Mock()
        recognizer.AcceptWaveform.return_value = False
        recognizer.PartialResult.return_value = '{"partial":""}'
        stream = io.BytesIO(self.wav().getvalue()[:-2])
        with (
            tempfile.TemporaryDirectory() as model,
            self.assertRaises(module.BenchmarkError),
        ):
            module.benchmark(
                stream,
                model,
                load_model=lambda _: object(),
                make_recognizer=lambda _: recognizer,
            )
        self.assertEqual(recognizer.AcceptWaveform.call_count, 2)
        recognizer.FinalResult.assert_not_called()
