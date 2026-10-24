"""Rule-based smoke-alarm detector for the standard T3 evacuation pattern (ISO 8201 / NFPA 72).

T3 = three 0.5 s beeps with 0.5 s gaps, then a 1.5 s pause, repeating. Most alarms beep a piezo tone near
3 kHz; some newer ones use a 520 Hz low tone. A 3 s clip always holds at least two beeps of the pattern.
ESC-50 has no smoke alarms, so this rule stands in for a trained class until we have recordings (issue #14).
It needs no embedding, so it works even when Gemini is slow or rate-limited.
"""

from dataclasses import dataclass

import numpy as np

from app.audio import SAMPLE_RATE

FRAME = 512  # 32 ms FFT window
HOP = 320  # 20 ms between frames
HOP_S = HOP / SAMPLE_RATE
BANDS_HZ = [(2500.0, 4000.0), (440.0, 620.0)]  # piezo alarms, 520 Hz low-tone alarms
SPECTRUM_HZ = (150.0, 7000.0)

MIN_TONALITY = 0.4  # share of a frame's energy in the alarm tone (±2 FFT bins)
MAX_LEVEL_DROP_DB = 15.0  # beep frames are within this much of the clip's loudest tonal frame
FREQ_TOLERANCE = 0.05  # beeps must stay within ±5% of the clip's median tone

BEEP_S = (0.3, 0.8)  # nominal 0.5 s
GAP_S = (0.3, 0.8)  # nominal 0.5 s, between beeps of one group
PAUSE_S = (1.1, 2.2)  # nominal 1.5 s, between groups
EDGE_BEEP_MIN_S = 0.1  # a beep cut off by the clip edge only has to be this long
MIN_BEEPS = 2


@dataclass(frozen=True)
class AlarmResult:
    detected: bool
    score: float  # mean tonality of the beep frames, 0–1
    tone_hz: float | None
    beeps: int


def _frames(samples: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Power spectrogram (frames × bins) and the bin frequencies."""
    n = 1 + (len(samples) - FRAME) // HOP
    idx = np.arange(FRAME)[None, :] + HOP * np.arange(n)[:, None]
    windowed = samples[idx] * np.hanning(FRAME)[None, :]
    power = np.abs(np.fft.rfft(windowed, axis=1)) ** 2
    return power, np.fft.rfftfreq(FRAME, 1 / SAMPLE_RATE)


def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """[start, end) frame ranges where mask is True."""
    edges = np.diff(np.concatenate(([0], mask.astype(np.int8), [0])))
    return list(zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)))


def _tone_frames(power: np.ndarray, freqs: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Per frame: tonality, energy (dB) and peak frequency of the strongest alarm-band tone."""
    spectrum = (freqs >= SPECTRUM_HZ[0]) & (freqs <= SPECTRUM_HZ[1])
    total = power[:, spectrum].sum(axis=1) + 1e-12
    best_tonality = np.zeros(len(power))
    best_energy = np.zeros(len(power))
    best_freq = np.zeros(len(power))
    for low, high in BANDS_HZ:
        band = np.flatnonzero((freqs >= low) & (freqs <= high))
        peak = band[np.argmax(power[:, band], axis=1)]
        rows = np.arange(len(power))
        tone = sum(power[rows, np.clip(peak + k, 0, len(freqs) - 1)] for k in range(-2, 3))
        tonality = tone / total
        better = tonality > best_tonality
        best_tonality[better] = tonality[better]
        best_energy[better] = tone[better]
        best_freq[better] = freqs[peak[better]]
    return best_tonality, 10 * np.log10(best_energy + 1e-12), best_freq


def _clean(mask: np.ndarray) -> np.ndarray:
    """Fill dropouts up to 2 frames inside a beep, then drop blips up to 2 frames."""
    mask = mask.copy()
    for start, end in _runs(~mask):
        if 0 < start and end < len(mask) and end - start <= 2:
            mask[start:end] = True
    for start, end in _runs(mask):
        if end - start <= 2:
            mask[start:end] = False
    return mask


def detect(samples: np.ndarray) -> AlarmResult:
    """Check one validated clip (float samples at 16 kHz) for the T3 smoke-alarm pattern."""
    if len(samples) < FRAME:
        return AlarmResult(False, 0.0, None, 0)
    tonality, level_db, freq = _tone_frames(*_frames(samples.astype(np.float64)))
    tonal = tonality >= MIN_TONALITY
    if not tonal.any():
        return AlarmResult(False, 0.0, None, 0)
    loud = level_db >= level_db[tonal].max() - MAX_LEVEL_DROP_DB
    candidate = tonal & loud
    tone_hz = float(np.median(freq[candidate]))
    steady = np.abs(freq - tone_hz) <= FREQ_TOLERANCE * tone_hz
    on = _clean(candidate & steady)

    last = len(on)
    beeps = []
    for start, end in _runs(on):
        seconds = (end - start) * HOP_S
        at_edge = start == 0 or end == last
        low = EDGE_BEEP_MIN_S if at_edge else BEEP_S[0]
        if not low <= seconds <= BEEP_S[1]:
            return AlarmResult(False, 0.0, tone_hz, len(beeps))  # a continuous or odd tone isn't T3
        beeps.append((start, end))
    if len(beeps) < MIN_BEEPS:
        return AlarmResult(False, 0.0, tone_hz, len(beeps))
    for (_, prev_end), (next_start, _) in zip(beeps, beeps[1:]):
        gap = (next_start - prev_end) * HOP_S
        if not (GAP_S[0] <= gap <= GAP_S[1] or PAUSE_S[0] <= gap <= PAUSE_S[1]):
            return AlarmResult(False, 0.0, tone_hz, len(beeps))
    complete = [b for b in beeps if b[0] != 0 and b[1] != last]
    if not complete:
        return AlarmResult(False, 0.0, tone_hz, len(beeps))

    score = float(np.mean(np.concatenate([tonality[s:e] for s, e in beeps])))
    return AlarmResult(True, round(score, 2), round(tone_hz), len(beeps))
