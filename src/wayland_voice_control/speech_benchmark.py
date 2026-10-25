"""Offline throughput measurements using the application's streaming decoder."""

import math
import time
import wave
from pathlib import Path

from .audio import load_local_model, make_recognizer
from .speech import StreamingDecoder


class BenchmarkError(RuntimeError):
    """Fixed benchmark failure without speech or dependency exception text."""


def benchmark(
    wav_source,
    model_path,
    *,
    clock=time.perf_counter,
    paced=False,
    sleep=time.sleep,
    load_model=load_local_model,
    make_recognizer=make_recognizer,
):
    """Read 4096-byte PCM blocks, return timings only; accept 0 < duration <= 60 s.

    Percentiles use nearest rank. Decode time sums accept/partial parsing and
    finalization time; file reads, model loading and recognizer creation are
    outside that measurement. A process-cold load can use the OS page cache.
    """
    failure = None
    decoder = None
    report = None
    try:
        path = Path(model_path).expanduser()
        if not path.is_dir() or "://" in str(model_path):
            raise BenchmarkError("Choose an existing local Vosk model directory.")
        with wave.open(wav_source, "rb") as stream:
            frames = stream.getnframes()
            if (
                stream.getnchannels() != 1
                or stream.getsampwidth() != 2
                or stream.getframerate() != 16000
                or stream.getcomptype() != "NONE"
                or not 0 < frames <= 960000
            ):
                raise BenchmarkError(
                    "Use an uncompressed mono 16 kHz 16-bit WAV, up to 60 seconds."
                )
            start = clock()
            model = load_model(path)
            cold_load = clock() - start
            decoder = StreamingDecoder(make_recognizer(model))
            replay_started = clock() if paced else None
            maximum_lag = 0.0
            chunks = []
            read_frames = 0
            while read_frames < frames:
                chunk = stream.readframes(min(2048, frames - read_frames))
                if not chunk or len(chunk) % 2:
                    raise BenchmarkError("The local WAV is truncated or invalid.")
                read_frames += len(chunk) // 2
                if paced:
                    arrival = replay_started + read_frames / 16000
                    delay = arrival - clock()
                    if delay > 0:
                        sleep(delay)
                start = clock()
                decoder.accept(chunk)
                end = clock()
                chunks.append(end - start)
                if paced:
                    maximum_lag = max(maximum_lag, end - arrival)
            start = clock()
            decoder.finish()  # Deliberately discard content; never print transcripts.
            finalization = clock() - start
            ordered = sorted(chunks)
            audio_seconds = frames / 16000
            decode_seconds = sum(chunks) + finalization
            report = {
                "cold_load_seconds": cold_load,
                "audio_seconds": audio_seconds,
                "decode_seconds": decode_seconds,
                "realtime_factor": decode_seconds / audio_seconds,
                "chunk_count": len(chunks),
                "chunk_p50_seconds": ordered[math.ceil(0.5 * len(chunks)) - 1],
                "chunk_p95_seconds": ordered[math.ceil(0.95 * len(chunks)) - 1],
                "chunk_max_seconds": max(chunks),
                "finalization_seconds": finalization,
                "partial_count": decoder.partial_count,
            }
            if paced:
                report["max_replay_lag_seconds"] = maximum_lag
    except BenchmarkError as error:
        failure = str(error)
    except Exception:  # noqa: BLE001 - never expose WAV/recognizer dependency messages
        failure = "Offline speech benchmark failed. Check the local WAV and model."
    finally:
        if decoder:
            decoder.clear()
    if failure:
        raise BenchmarkError(failure)
    return report
