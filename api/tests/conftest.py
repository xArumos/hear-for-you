import dataclasses
import io
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from app import gemini, ratelimit, store
from app.errors import UpstreamError
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


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Any Gemini call a test didn't fake fails like an outage instead of reaching the network."""

    def offline() -> None:
        raise UpstreamError("Network is disabled in tests.")

    monkeypatch.setattr(gemini, "_get_client", offline)


@pytest.fixture(autouse=True)
def reset_limiters() -> None:
    """Each test starts with empty rate-limit windows so tests don't throttle each other."""
    ratelimit.detect_limiter.reset()
    ratelimit.describe_limiter.reset()


@pytest.fixture(autouse=True)
def temp_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """Point the app's default database at a fresh seeded file so route tests never touch ./hearalert.db."""
    path = str(tmp_path / "app.db")
    monkeypatch.setattr(store, "settings", dataclasses.replace(store.settings, db_path=path))
    store.init_db()
    return path


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
