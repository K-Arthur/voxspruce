"""Capture actual native fd 2 writes in subprocesses, never a host microphone."""

import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
import wave
from pathlib import Path


@unittest.skipUnless(
    importlib.util.find_spec("vosk"), "optional Vosk dependency absent"
)
class NativeVoskPrivacyTests(unittest.TestCase):
    project = Path(__file__).resolve().parents[1]

    def run_local(self, arguments):
        return subprocess.run(
            [sys.executable, *arguments],
            cwd=self.project,
            env=dict(os.environ, PYTHONPATH=str(self.project / "src")),
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )

    def test_actual_benchmark_invalid_local_model_has_only_fixed_stderr(self):
        with tempfile.TemporaryDirectory(prefix="secret-private-model-") as directory:
            root = Path(directory)
            model = root / "model"
            model.mkdir()
            audio = root / "silence.wav"
            with wave.open(str(audio), "wb") as stream:
                stream.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
                stream.writeframes(b"\0" * 4096)
            for corrupt_config in (False, True):
                if corrupt_config:
                    (model / "am").mkdir()
                    (model / "conf").mkdir()
                    (model / "am/final.mdl").write_bytes(b"invalid model")
                    (model / "conf/model.conf").write_text(
                        "--secret-private-config=invalid\n"
                    )
                with self.subTest(corrupt_config=corrupt_config):
                    result = self.run_local(
                        [
                            "scripts/benchmark-speech.py",
                            "--model",
                            str(model),
                            "--wav",
                            str(audio),
                        ]
                    )
                    self.assertEqual(result.returncode, 1)
                    self.assertEqual(result.stdout, "")
                    self.assertEqual(
                        result.stderr,
                        "Offline speech benchmark failed. Check the local WAV and model.\n",
                    )

    def test_actual_prepare_empty_and_corrupt_models_suppress_private_native_errors(self):
        code = """
import sys
from wayland_voice_control.audio import AudioCapture
capture = AudioCapture(dispatch=lambda callback: callback(), run_worker=lambda job: job(),
                       spawn=lambda: (_ for _ in ()).throw(AssertionError("unexpected mic")))
capture.prepare(sys.argv[1], on_state=lambda value: None, on_error=lambda error: print(error))
"""
        for corrupt_config in (False, True):
            with (
                self.subTest(corrupt_config=corrupt_config),
                tempfile.TemporaryDirectory(
                    prefix="secret-private-model-"
                ) as directory,
            ):
                model = Path(directory)
                if corrupt_config:
                    (model / "am").mkdir()
                    (model / "conf").mkdir()
                    (model / "am/final.mdl").write_bytes(b"invalid model")
                    (model / "conf/model.conf").write_text(
                        "--secret-private-config=invalid\n"
                    )
                result = self.run_local(["-c", code, directory])
                self.assertEqual(result.returncode, 0)
                if corrupt_config:
                    # Kaldi prints generic usage outside its log handler. It must
                    # contain no dependency error, private path or config contents.
                    self.assertNotIn(directory, result.stderr)
                    self.assertNotIn("secret-private", result.stderr)
                    self.assertNotIn("ERROR", result.stderr)
                else:
                    self.assertEqual(result.stderr, "")
                self.assertEqual(
                    result.stdout,
                    "Local model preparation failed. Check the model directory.\n",
                )

    def test_actual_decode_error_is_silent_after_shared_model_loader(self):
        model = self.project / "models/vosk-model-small-en-us-0.15"
        if not model.is_dir():
            self.skipTest("optional local model fixture absent")
        # This actual model expects 16 kHz; 8 kHz deliberately exercises Vosk's
        # native feature-pipeline error. All PCM is generated silence.
        code = """
import sys, vosk
from wayland_voice_control.audio import load_local_model
from wayland_voice_control.speech import StreamingDecoder
model = load_local_model(sys.argv[1])
recognizer = vosk.KaldiRecognizer(model, 8000)
try:
    StreamingDecoder(recognizer).accept(b"\\0" * 4096)
except Exception:
    print("fixed recognition failure")
"""
        result = self.run_local(["-c", code, str(model)])
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "fixed recognition failure\n")
        self.assertEqual(result.stderr, "")
