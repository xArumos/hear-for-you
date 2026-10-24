"""WAV validation. Runs before any Gemini call, so a bad clip costs nothing."""

import io

import numpy as np
import soundfile as sf

from app.errors import BadAudio

SAMPLE_RATE = 16_000
CLIP_SECONDS = 3.0
ROOM_SECONDS = 10.0
LENGTH_TOLERANCE_S = 0.01
SILENCE_DBFS = -60.0


def peak_dbfs(samples: np.ndarray) -> float:
    peak = float(np.max(np.abs(samples))) if samples.size else 0.0
    return 20.0 * float(np.log10(peak)) if peak > 0 else float("-inf")


def validate_clip(data: bytes, seconds: float = CLIP_SECONDS) -> np.ndarray:
    """Check a 16 kHz mono 16-bit PCM WAV of `seconds` length; return float samples in [-1, 1]."""
    expected = f"Clip must be 16 kHz mono 16-bit WAV, {seconds:.1f} s."
    try:
        info = sf.info(io.BytesIO(data))
    except (RuntimeError, sf.LibsndfileError):
        raise BadAudio(f"Not a readable WAV file. {expected}")

    if info.format != "WAV" or info.subtype != "PCM_16":
        raise BadAudio(f"Got {info.format}/{info.subtype}. {expected}")
    if info.samplerate != SAMPLE_RATE:
        raise BadAudio(f"Got {info.samplerate} Hz. {expected}")
    if info.channels != 1:
        raise BadAudio(f"Got {info.channels} channels. {expected}")
    if abs(info.frames / SAMPLE_RATE - seconds) > LENGTH_TOLERANCE_S:
        raise BadAudio(f"Got {info.frames / SAMPLE_RATE:.2f} s. {expected}")

    samples, _ = sf.read(io.BytesIO(data), dtype="float32")
    if peak_dbfs(samples) < SILENCE_DBFS:
        raise BadAudio("Clip is silent.")
    return samples
