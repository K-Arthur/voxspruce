import importlib.util
import sys
import unittest
from pathlib import Path


class BenchmarkIsolationTests(unittest.TestCase):
    def setUp(self):
        path = Path(__file__).resolve().parents[1] / "scripts/benchmark-speech.py"
        spec = importlib.util.spec_from_file_location("benchmark_cli", path)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)

    def test_child_output_is_bounded_validated_and_failure_is_not_forwarded(self):
        self.assertTrue(hasattr(self.module, "isolated_report"))
        for program in (
            "print('x' * 9000)",
            'print(\'{"transcript":"private speech"}\')',
            "raise RuntimeError('private speech')",
            "print('invalid json')",
        ):
            with self.subTest(program=program):
                self.assertIsNone(
                    self.module.isolated_report([sys.executable, "-c", program])
                )

    def test_child_timeout_is_bounded_and_reaped(self):
        self.assertTrue(hasattr(self.module, "isolated_report"))
        self.assertIsNone(
            self.module.isolated_report(
                [sys.executable, "-c", "import time;time.sleep(10)"], timeout=0.05
            )
        )

    def test_help_and_argument_errors_keep_normal_exit_statuses(self):
        import subprocess

        script = Path(__file__).resolve().parents[1] / "scripts/benchmark-speech.py"
        help_result = subprocess.run(
            [sys.executable, str(script), "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(help_result.returncode, 0)
        self.assertIn("--paced", help_result.stdout)
        self.assertNotIn("--_worker", help_result.stdout)
        self.assertEqual(help_result.stderr, "")
        invalid_result = subprocess.run(
            [sys.executable, str(script)], capture_output=True, text=True, check=False
        )
        self.assertEqual(invalid_result.returncode, 2)

    def test_only_expected_finite_metadata_can_pass_from_child(self):
        import json

        report = {
            "cold_load_seconds": 1.0,
            "audio_seconds": 2.0,
            "decode_seconds": 0.5,
            "realtime_factor": 0.25,
            "chunk_count": 1,
            "chunk_p50_seconds": 0.3,
            "chunk_p95_seconds": 0.3,
            "chunk_max_seconds": 0.3,
            "finalization_seconds": 0.2,
            "partial_count": 1,
            "chunk_bytes": 4096,
            "platform": "test",
            "python": "test",
            "cpu": "test",
            "vosk": "test",
            "model": "test",
        }
        program = "print(" + repr(json.dumps(report)) + ")"
        self.assertEqual(
            self.module.isolated_report([sys.executable, "-c", program]), report
        )
        report["decode_seconds"] = float("nan")
        program = "print(" + repr(json.dumps(report)) + ")"
        self.assertIsNone(self.module.isolated_report([sys.executable, "-c", program]))
