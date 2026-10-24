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


def validate_clip(
    data: bytes, seconds: float = CLIP_SECONDS, allow_silent: bool = False
) -> np.ndarray:
    """Check a 16 kHz mono 16-bit PCM WAV of `seconds` length; return float samples in [-1, 1].

    `allow_silent` is for the room clip, where a very quiet room is valid input.
    """
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
    if not allow_silent and peak_dbfs(samples) < SILENCE_DBFS:
        raise BadAudio("Clip is silent.")
    return samples


def to_wav(samples: np.ndarray) -> bytes:
    buf = io.BytesIO()
    sf.write(buf, samples, SAMPLE_RATE, format="WAV", subtype="PCM_16")
    return buf.getvalue()


def room_windows(samples: np.ndarray, count: int = 3) -> list[bytes]:
    """Split a validated room clip into `count` evenly spaced CLIP_SECONDS windows, each as a WAV."""
    width = int(CLIP_SECONDS * SAMPLE_RATE)
    starts = np.linspace(0, len(samples) - width, count).astype(int)
    return [to_wav(samples[start : start + width]) for start in starts]
