#!/usr/bin/env python3
"""Measure local WAV decoding without microphone, network or transcript output."""

import argparse
import importlib.metadata
import json
import math
import os
import platform
import select
import subprocess
import sys
import time
from pathlib import Path

from wayland_voice_control.speech_benchmark import benchmark


def isolated_report(command, *, timeout=120):
    """Bound native child output/time; forward only validated timing metadata."""
    process = None
    try:
        process = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
        )
        deadline, payload = time.monotonic() + timeout, bytearray()
        while True:
            remaining = deadline - time.monotonic()
            if (
                remaining <= 0
                or not select.select([process.stdout], [], [], remaining)[0]
            ):
                return None
            chunk = os.read(process.stdout.fileno(), 4096)
            if not chunk:
                break
            payload.extend(chunk)
            if len(payload) > 8192:
                return None
        if process.wait(timeout=max(0, deadline - time.monotonic())) != 0:
            return None
        report = json.loads(payload)
        strings = {"platform", "python", "cpu", "vosk", "model"}
        numbers = {
            "cold_load_seconds",
            "audio_seconds",
            "decode_seconds",
            "realtime_factor",
            "chunk_count",
            "chunk_p50_seconds",
            "chunk_p95_seconds",
            "chunk_max_seconds",
            "finalization_seconds",
            "partial_count",
            "chunk_bytes",
        }
        if not isinstance(report, dict) or set(report) not in (
            strings | numbers,
            strings | numbers | {"max_replay_lag_seconds"},
        ):
            return None
        if any(
            not isinstance(report[key], str) or len(report[key]) > 512
            for key in strings
        ):
            return None
        if any(
            type(report[key]) not in (int, float)
            or not math.isfinite(report[key])
            or report[key] < 0
            for key in set(report) - strings
        ):
            return None
        return report
    except Exception:  # noqa: BLE001 - never forward child/dependency errors or payloads
        return None
    finally:
        if process:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=1)
            process.stdout.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model", required=True, help="Existing local Vosk model directory"
    )
    parser.add_argument(
        "--wav", required=True, help="Local mono 16 kHz 16-bit PCM WAV, <=60 s"
    )
    parser.add_argument(
        "--paced",
        action="store_true",
        help="Replay at audio arrival rate and measure accumulated decode lag",
    )
    parser.add_argument("--_worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not args._worker:
        command = [
            sys.executable,
            str(Path(__file__).resolve()),
            "--_worker",
            "--model",
            args.model,
            "--wav",
            args.wav,
        ]
        if args.paced:
            command.append("--paced")
        report = isolated_report(command)
        if report is None:
            print(
                "Offline speech benchmark failed. Check the local WAV and model.",
                file=sys.stderr,
            )
            return 1
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    try:
        # Open only a local file. wave.open accepts file-like objects as well.
        with Path(args.wav).expanduser().open("rb") as stream:
            report = benchmark(stream, args.model, paced=args.paced)
        cpu = platform.processor()
        try:
            cpu = next(
                line.split(":", 1)[1].strip()
                for line in Path("/proc/cpuinfo").read_text().splitlines()
                if line.startswith("model name")
            )
        except (OSError, StopIteration):
            pass
        report.update(
            platform=platform.platform(),
            python=platform.python_version(),
            cpu=cpu,
            vosk=importlib.metadata.version("vosk"),
            model=Path(args.model).name,
            chunk_bytes=4096,
        )
    except Exception:  # noqa: BLE001 - child failures never expose dependency tracebacks
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
