import io

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from app import gemini, smoke_alarm, store
from app.errors import UpstreamError
from tests.test_routes import post_detect

RATE = 16_000
CLIP = 3 * RATE


def t3(seconds: float, freq: float, square: bool = False) -> np.ndarray:
    """The T3 pattern: three 0.5 s beeps 0.5 s apart, then a 1.5 s pause, repeating."""
    t = np.arange(int(seconds * RATE)) / RATE
    phase = t % 4.0
    gate = (phase < 0.5) | ((phase >= 1.0) & (phase < 1.5)) | ((phase >= 2.0) & (phase < 2.5))
    tone = np.sin(2 * np.pi * freq * t)
    return 0.6 * (np.sign(tone) if square else tone) * gate


def with_noise(x: np.ndarray, snr_db: float) -> np.ndarray:
    noise = np.random.default_rng(42).standard_normal(len(x))
    noise *= np.sqrt(np.mean(x**2) / np.mean(noise**2)) / 10 ** (snr_db / 20)
    return x + noise


def to_wav(x: np.ndarray) -> bytes:
    buf = io.BytesIO()
    sf.write(buf, np.clip(x, -1, 1).astype(np.float32), RATE, format="WAV", subtype="PCM_16")
    return buf.getvalue()


@pytest.mark.parametrize(
    ("freq", "square", "snr_db"),
    [(3100, False, 10), (3400, False, 5), (520, True, 20)],
    ids=["3.1kHz", "3.4kHz_noisy", "520Hz_square"],
)
def test_t3_detected_at_every_offset(freq: float, square: bool, snr_db: float) -> None:
    signal = with_noise(t3(8.0, freq, square), snr_db)
    offsets = range(0, 4 * RATE, RATE // 5)  # one full 4 s T3 period, every 0.2 s
    for offset in offsets:
        result = smoke_alarm.detect(signal[offset : offset + CLIP])
        assert result.detected, f"missed at offset {offset / RATE:.1f} s"
        assert result.tone_hz == pytest.approx(freq, rel=0.05)
        assert 0 < result.score <= 1


T = np.arange(CLIP) / RATE
NOT_ALARMS = {
    "continuous_tone": 0.6 * np.sin(2 * np.pi * 3100 * T),
    "fast_beeping": 0.6 * np.sin(2 * np.pi * 3100 * T) * ((T % 0.4) < 0.2),
    "short_triple_beep": 0.6 * np.sin(2 * np.pi * 2800 * T) * (((T % 0.3) < 0.15) & (T < 0.9)),
    "single_beep": 0.6 * np.sin(2 * np.pi * 3100 * T) * ((T > 1) & (T < 1.5)),
    "beeps_outside_alarm_bands": 0.6 * np.sin(2 * np.pi * 1000 * T) * ((T % 1) < 0.5),
    "white_noise": 0.3 * np.random.default_rng(1).standard_normal(CLIP),
    "chord": 0.2 * sum(np.sin(2 * np.pi * f * T) for f in (440, 660, 880)),
}


@pytest.mark.parametrize("name", NOT_ALARMS)
def test_other_sounds_are_not_alarms(name: str) -> None:
    assert not smoke_alarm.detect(NOT_ALARMS[name]).detected


def alarm_wav() -> bytes:
    return to_wav(with_noise(t3(4.0, 3100), 20)[RATE // 2 : RATE // 2 + CLIP])


def test_detect_returns_smoke_alarm_without_gemini(
    client: TestClient, embed_calls: list[bytes]
) -> None:
    body = post_detect(client, alarm_wav()).json()
    assert body["kind"] == "builtin"
    assert body["sound_id"] == "builtin_smoke_alarm" and body["label"] == "Smoke alarm"
    assert 0 < body["confidence"] <= 1 and body["description"] is None
    assert embed_calls == []
    [event] = store.list_events()
    assert event["event_id"] == body["event_id"]


def test_smoke_alarm_ignores_rate_limit_and_outages(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def down(wav: bytes) -> None:
        raise UpstreamError("Gemini is down.")

    monkeypatch.setattr(gemini, "embed_audio", down)
    for _ in range(3):  # back to back, well over the 1/s detect cap
        assert post_detect(client, alarm_wav()).json()["sound_id"] == "builtin_smoke_alarm"


def test_disabled_smoke_alarm_falls_through(client: TestClient, embed_calls: list[bytes]) -> None:
    store.update_sound("builtin_smoke_alarm", enabled=False)
    body = post_detect(client, alarm_wav(), level_db="-40").json()
    assert body["kind"] == "none"
    assert len(embed_calls) == 1
