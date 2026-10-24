"""Convert audio to Hear For You's loudest three-second PCM WAV window."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import tempfile
import wave

import numpy as np

RATE = 16_000
SAMPLES = 48_000
PREPROCESS_VERSION = "pcm16-16k-mono-maxenergy-earliest-v1"
BACKGROUND_VERSION = "pcm16-16k-mono-contiguous3s-v1"


def loudest_start(samples: np.ndarray) -> int:
    """Choose maximum energy, resolving ties to the earliest sample."""
    if samples.ndim != 1 or len(samples) < SAMPLES:
        raise ValueError("Audio must contain at least 3.0 seconds after resampling.")
    values = samples.astype(np.int64)
    energy = np.concatenate(([0], np.cumsum(values * values, dtype=np.int64)))
    totals = energy[SAMPLES:] - energy[:-SAMPLES]
    start = int(np.argmax(totals))
    if totals[start] == 0:
        raise ValueError("Audio is silent; choose a recording containing a sound.")
    return start


def loudest_window(samples: np.ndarray) -> np.ndarray:
    start = loudest_start(samples)
    return samples[start:start + SAMPLES].astype("<i2")


def validate_wav(path: Path) -> bytes:
    """Return validated PCM bytes, rejecting malformed and silent clips."""
    try:
        with wave.open(str(path), "rb") as audio:
            if (audio.getframerate(), audio.getnchannels(), audio.getsampwidth(),
                    audio.getnframes(), audio.getcomptype()) != (RATE, 1, 2, SAMPLES, "NONE"):
                raise ValueError(f"{path.name}: expected 16 kHz mono PCM16 WAV, 3.0 s.")
            pcm = audio.readframes(SAMPLES)
    except (wave.Error, EOFError) as exc:
        raise ValueError(f"{path.name}: invalid PCM WAV.") from exc
    if len(pcm) != SAMPLES * 2 or not np.any(np.frombuffer(pcm, dtype="<i2")):
        raise ValueError(f"{path.name}: truncated or silent WAV.")
    return pcm


def convert_audio(source: Path, destination: Path) -> Path:
    """Decode with ffmpeg, select a window, and atomically write a WAV."""
    try:
        result = subprocess.run(
            ["ffmpeg", "-nostdin", "-v", "error", "-i", str(source), "-map", "0:a:0",
             "-ac", "1", "-ar", str(RATE), "-c:a", "pcm_s16le", "-f", "s16le", "pipe:1"],
            capture_output=True, check=False, timeout=60,
        )
    except FileNotFoundError as exc:
        raise ValueError("ffmpeg is required; install it before converting audio.") from exc
    if result.returncode or len(result.stdout) % 2:
        raise ValueError(f"{source.name}: ffmpeg could not decode audio.")
    window = loudest_window(np.frombuffer(result.stdout, dtype="<i2"))
    write_pcm_wav(destination, window.tobytes())
    return destination


def write_pcm_wav(destination: Path, pcm: bytes) -> None:
    """Atomically store exactly one non-silent three-second PCM window."""
    if len(pcm) != SAMPLES * 2 or not np.any(np.frombuffer(pcm, dtype="<i2")):
        raise ValueError("Expected 48,000 non-silent PCM16 samples.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=destination.parent, suffix=".wav")
    os.close(fd)
    temporary = Path(name)
    try:
        with wave.open(str(temporary), "wb") as audio:
            audio.setparams((1, 2, RATE, SAMPLES, "NONE", "not compressed"))
            audio.writeframes(pcm)
        validate_wav(temporary)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    try:
        convert_audio(args.source, args.destination)
    except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
        parser.exit(1, f"Conversion failed: {exc}\n")


if __name__ == "__main__":
    main()
