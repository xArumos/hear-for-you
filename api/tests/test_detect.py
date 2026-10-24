import numpy as np
import pytest
from fastapi.testclient import TestClient

from app import detectors, gemini, ratelimit, store
from app.detectors import TaughtScore
from tests.conftest import make_wav
from tests.test_routes import post_detect
from tests.test_teach import basis

KNOCK = basis((0, 1.0))
ROOM = np.stack([basis((5, 1.0)), basis((6, 1.0))])
DETECT_FIELDS = {"event_id", "kind", "label", "sound_id", "confidence", "description", "latency_ms"}


def embed_as(monkeypatch: pytest.MonkeyPatch, vec: np.ndarray) -> None:
    monkeypatch.setattr(gemini, "embed_audio", lambda wav: vec)


def add_knock(name: str = "Door knock", prototype: np.ndarray = KNOCK) -> str:
    return str(store.add_sound(name, "door", prototype, ROOM, 0.6)["sound_id"])


def test_taught_match(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    sound_id = add_knock()
    embed_as(monkeypatch, basis((0, 1.0), (1, 0.3)))
    res = post_detect(client, make_wav())
    assert res.status_code == 200
    body = res.json()
    assert set(body) == DETECT_FIELDS
    assert body["kind"] == "taught"
    assert body["label"] == "Door knock" and body["sound_id"] == sound_id
    assert 0.5 <= body["confidence"] <= 1.0
    assert body["description"] is None
    [event] = store.list_events()
    assert event["event_id"] == body["event_id"] and event["kind"] == "taught"


def test_taught_match_ignores_loudness(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    add_knock()
    embed_as(monkeypatch, KNOCK)
    assert post_detect(client, make_wav(), level_db="-5").json()["kind"] == "taught"


def test_best_of_two_matches_wins(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    add_knock("Knock A", basis((0, 1.0), (1, 1.0)))
    b = add_knock("Knock B", basis((0, 1.0), (1, 0.1)))
    embed_as(monkeypatch, KNOCK)
    assert post_detect(client, make_wav()).json()["sound_id"] == b


def test_disabled_sound_is_skipped(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    store.update_sound(add_knock(), enabled=False)
    embed_as(monkeypatch, KNOCK)
    assert post_detect(client, make_wav()).json()["kind"] == "none"
    assert store.list_events() == []


def test_closer_to_room_is_not_a_match(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    add_knock()
    embed_as(monkeypatch, basis((0, 1.0), (5, 1.1)))  # above threshold, but nearer the room
    assert post_detect(client, make_wav()).json()["kind"] == "none"


def test_loud_unknown_is_described(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    add_knock()
    embed_as(monkeypatch, basis((9, 1.0)))
    described: list[bytes] = []

    def fake_describe(wav: bytes) -> str:
        described.append(wav)
        return "A kettle whistling on the stove."

    monkeypatch.setattr(gemini, "describe_audio", fake_describe)
    wav = make_wav()
    body = post_detect(client, wav, level_db="-12.5").json()
    assert set(body) == DETECT_FIELDS
    assert body["kind"] == "unknown"
    assert body["description"] == "A kettle whistling on the stove."
    assert body["label"] is None and body["sound_id"] is None and body["confidence"] is None
    assert described == [wav]
    [event] = store.list_events()
    assert event["event_id"] == body["event_id"] and event["description"] == body["description"]


def test_unknown_with_failed_describe(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    embed_as(monkeypatch, basis((9, 1.0)))  # describe_audio hits the offline client and returns None
    body = post_detect(client, make_wav(), level_db="-12.5").json()
    assert body["kind"] == "unknown" and body["description"] is None
    assert len(store.list_events()) == 1


def test_quiet_unmatched_is_none(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    embed_as(monkeypatch, basis((9, 1.0)))
    monkeypatch.setattr(gemini, "describe_audio", lambda wav: pytest.fail("should not describe"))
    body = post_detect(client, make_wav(), level_db="-20").json()  # at the cutoff is not loud
    assert body["kind"] == "none"
    assert store.list_events() == []


@pytest.mark.parametrize(
    ("score", "expected"), [(0.6, 0.5), (0.8, 0.75), (1.0, 1.0)], ids=["at_threshold", "mid", "perfect"]
)
def test_taught_confidence(score: float, expected: float) -> None:
    assert detectors.taught_confidence(TaughtScore(score, 0.0, 0.6)) == pytest.approx(expected)


def test_describe_cap_skips_gemini(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    embed_as(monkeypatch, basis((9, 1.0)))
    described: list[bytes] = []
    monkeypatch.setattr(gemini, "describe_audio", lambda wav: described.append(wav) or "A dog barking.")
    first = post_detect(client, make_wav(), level_db="-6").json()
    ratelimit.detect_limiter.reset()
    second = post_detect(client, make_wav(), level_db="-6").json()
    assert first["description"] == "A dog barking."
    assert second["kind"] == "unknown" and second["description"] is None
    assert len(described) == 1
    assert len(store.list_events()) == 2
