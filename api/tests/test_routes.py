import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app import gemini, store
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


def add_taught(name: str = "Kettle") -> str:
    vec = np.zeros(768, dtype=np.float32)
    vec[0] = 1.0
    return str(store.add_sound(name, "kettle", vec, np.stack([vec, vec]), 0.7)["sound_id"])


def test_list_sounds(client: TestClient) -> None:
    sound_id = add_taught()
    res = client.get("/api/sounds")
    assert res.status_code == 200
    body = res.json()
    assert set(body) == {"sounds", "latency_ms"}
    assert isinstance(body["latency_ms"], int)
    sounds = body["sounds"]
    assert [s["sound_id"] for s in sounds[:6]] == [b[0] for b in store.BUILTINS]
    assert sounds[-1] == {
        "sound_id": sound_id, "name": "Kettle", "icon": "kettle", "kind": "taught", "enabled": True,
    }
    for s in sounds:
        assert set(s) == {"sound_id", "name", "icon", "kind", "enabled"}


def test_patch_sound(client: TestClient) -> None:
    res = client.patch("/api/sounds/builtin_siren", json={"enabled": False, "name": "Ambulance"})
    assert res.status_code == 200
    body = res.json()
    assert body.pop("latency_ms") >= 0
    assert body == {
        "sound_id": "builtin_siren", "name": "Ambulance", "icon": "siren",
        "kind": "builtin", "enabled": False,
    }
    res = client.patch("/api/sounds/builtin_siren", json={"enabled": True})
    assert res.json()["enabled"] is True and res.json()["name"] == "Ambulance"


@pytest.mark.parametrize(
    "payload", [{}, {"name": ""}, {"name": "x" * 41}, {"enabled": "maybe"}],
    ids=["empty", "blank_name", "long_name", "bad_enabled"],
)
def test_patch_sound_bad_request(client: TestClient, payload: dict[str, object]) -> None:
    res = client.patch("/api/sounds/builtin_siren", json=payload)
    assert res.status_code == 422
    assert_error_shape(res.json(), "bad_request")


def test_patch_unknown_sound(client: TestClient) -> None:
    res = client.patch("/api/sounds/snd_nope", json={"enabled": False})
    assert res.status_code == 404
    assert_error_shape(res.json(), "not_found")


def test_delete_taught_sound(client: TestClient) -> None:
    sound_id = add_taught()
    res = client.delete(f"/api/sounds/{sound_id}")
    assert res.status_code == 200
    body = res.json()
    assert body["deleted"] is True and isinstance(body["latency_ms"], int)
    assert set(body) == {"deleted", "latency_ms"}
    assert client.delete(f"/api/sounds/{sound_id}").status_code == 404


def test_delete_builtin_rejected(client: TestClient) -> None:
    res = client.delete("/api/sounds/builtin_siren")
    assert res.status_code == 422
    assert_error_shape(res.json(), "bad_request")


def test_history(client: TestClient) -> None:
    a = store.add_event("builtin", "Siren", "builtin_siren", 0.8, None)
    b = store.add_event("unknown", None, None, None, "A kettle whistling.")
    res = client.get("/api/history")
    assert res.status_code == 200
    body = res.json()
    assert set(body) == {"events", "latency_ms"}
    assert [e["event_id"] for e in body["events"]] == [b["event_id"], a["event_id"]]
    assert body["events"][0] == b
    assert len(client.get("/api/history", params={"limit": 1}).json()["events"]) == 1


def test_history_since(client: TestClient) -> None:
    store.add_event("builtin", "Siren", "builtin_siren", 0.8, None)
    events = client.get("/api/history", params={"since": "2000-01-01T00:00:00.000Z"}).json()["events"]
    assert len(events) == 1
    future = client.get("/api/history", params={"since": "2999-01-01T00:00:00+00:00"}).json()
    assert future["events"] == []


@pytest.mark.parametrize(
    "params", [{"limit": "0"}, {"limit": "lots"}, {"since": "yesterday"}],
    ids=["zero_limit", "text_limit", "bad_since"],
)
def test_history_bad_request(client: TestClient, params: dict[str, str]) -> None:
    res = client.get("/api/history", params=params)
    assert res.status_code == 422
    assert_error_shape(res.json(), "bad_request")
