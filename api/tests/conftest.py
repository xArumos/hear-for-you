import io

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from app import gemini
from app.main import app


def make_wav(
    seconds: float = 3.0,
    rate: int = 16_000,
    channels: int = 1,
    subtype: str = "PCM_16",
    amplitude: float = 0.5,
) -> bytes:
    frames = int(round(seconds * rate))
    t = np.arange(frames) / rate
    tone = (amplitude * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    data = np.stack([tone] * channels, axis=1) if channels > 1 else tone
    buf = io.BytesIO()
    sf.write(buf, data, rate, format="WAV", subtype=subtype)
    return buf.getvalue()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def embed_calls(monkeypatch: pytest.MonkeyPatch) -> list[bytes]:
    """Replace gemini.embed_audio with a fake that records calls and never hits the network."""
    calls: list[bytes] = []

    def fake_embed(wav: bytes) -> np.ndarray:
        calls.append(wav)
        vec = np.ones(768, dtype=np.float32)
        return vec / np.linalg.norm(vec)

    monkeypatch.setattr(gemini, "embed_audio", fake_embed)
    return calls
