#!/usr/bin/env python3
"""Measure local WAV decoding without microphone, network or transcript output."""

import argparse
import importlib.metadata
import json
import platform
import sys
from pathlib import Path

from wayland_voice_control.speech_benchmark import BenchmarkError, benchmark


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
    args = parser.parse_args()
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
    except (BenchmarkError, OSError):
        print(
            "Offline speech benchmark failed. Check the local WAV and model.",
            file=sys.stderr,
        )
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
