import httpx
import pytest
from fastapi.testclient import TestClient

from app import gemini
from app.errors import RateLimited, UpstreamError
from tests.conftest import make_wav


def post_detect(client: TestClient, wav: bytes, level_db: str | None = "-12.5") -> httpx.Response:
    data = {"level_db": level_db} if level_db is not None else {}
    return client.post(
        "/api/detect", files={"clip": ("clip.wav", wav, "audio/wav")}, data=data
    )


def assert_error_shape(body: dict[str, object], code: str) -> None:
    assert set(body) == {"error"}
    error = body["error"]
    assert isinstance(error, dict)
    assert error["code"] == code
    assert isinstance(error["message"], str) and error["message"]


def test_health(client: TestClient) -> None:
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json() == {
        "ok": True,
        "models": {"embed": "gemini-embedding-2", "describe": "gemini-3.8-flash"},
    }


def test_detect_returns_none(client: TestClient, embed_calls: list[bytes]) -> None:
    wav = make_wav()
    res = post_detect(client, wav)
    assert res.status_code == 200
    body = res.json()
    assert set(body) == {
        "event_id", "kind", "label", "sound_id", "confidence", "description", "latency_ms",
    }
    assert body["kind"] == "none"
    assert body["event_id"].startswith("evt_")
    assert body["label"] is None and body["sound_id"] is None
    assert body["confidence"] is None and body["description"] is None
    assert isinstance(body["latency_ms"], int) and body["latency_ms"] >= 0
    assert embed_calls == [wav]


def test_detect_bad_audio_skips_gemini(client: TestClient, embed_calls: list[bytes]) -> None:
    res = post_detect(client, make_wav(channels=2))
    assert res.status_code == 400
    assert_error_shape(res.json(), "bad_audio")
    assert embed_calls == []


@pytest.mark.parametrize("level_db", [None, "loud"], ids=["missing", "not_a_number"])
def test_detect_bad_level_db(
    client: TestClient, embed_calls: list[bytes], level_db: str | None
) -> None:
    res = post_detect(client, make_wav(), level_db=level_db)
    assert res.status_code == 422
    assert_error_shape(res.json(), "bad_request")
    assert embed_calls == []


def test_detect_missing_clip(client: TestClient, embed_calls: list[bytes]) -> None:
    res = client.post("/api/detect", data={"level_db": "-10"})
    assert res.status_code == 422
    assert_error_shape(res.json(), "bad_request")


def test_detect_gemini_rate_limited(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_embed(wav: bytes) -> None:
        raise RateLimited("Gemini rate limit reached.", retry_after_ms=1000)

    monkeypatch.setattr(gemini, "embed_audio", fake_embed)
    res = post_detect(client, make_wav())
    assert res.status_code == 429
    body = res.json()
    assert_error_shape(body, "rate_limited")
    assert body["error"]["retry_after_ms"] == 1000


def test_detect_gemini_upstream_error(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_embed(wav: bytes) -> None:
        raise UpstreamError("Gemini failed after one retry.")

    monkeypatch.setattr(gemini, "embed_audio", fake_embed)
    res = post_detect(client, make_wav())
    assert res.status_code == 502
    assert_error_shape(res.json(), "upstream_error")


def test_detect_over_cap_returns_429(client: TestClient, embed_calls: list[bytes]) -> None:
    assert post_detect(client, make_wav()).status_code == 200
    res = post_detect(client, make_wav())
    assert res.status_code == 429
    body = res.json()
    assert_error_shape(body, "rate_limited")
    assert body["error"]["retry_after_ms"] > 0
    assert len(embed_calls) == 1
