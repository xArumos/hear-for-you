import logging

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app import detectors, gemini, ongoing, ratelimit, store
from app.detectors import TaughtScore
from app.gemini import Described
from tests.conftest import make_wav
from tests.test_routes import post_detect
from tests.test_teach import basis

KNOCK = basis((0, 1.0))
ROOM = np.stack([basis((5, 1.0)), basis((6, 1.0))])
DETECT_FIELDS = {"event_id", "kind", "label", "sound_id", "confidence", "description", "latency_ms"}


def embed_as(monkeypatch: pytest.MonkeyPatch, vec: np.ndarray) -> None:
    monkeypatch.setattr(gemini, "embed_audio", lambda wav: vec)


def describe_as(monkeypatch: pytest.MonkeyPatch, result: Described | None) -> list[bytes]:
    calls: list[bytes] = []

    def fake(wav: bytes) -> Described | None:
        calls.append(wav)
        return result

    monkeypatch.setattr(gemini, "describe_relevance", fake)
    return calls


def again(client: TestClient, level_db: str = "-30") -> dict[str, object]:
    """Another detect right away, past the 1/s detect cap."""
    ratelimit.detect_limiter.reset()
    return dict(post_detect(client, make_wav(), level_db=level_db).json())


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


def test_disabled_taught_match_is_not_unknown(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    store.update_sound(add_knock(), enabled=False)
    embed_as(monkeypatch, KNOCK)
    calls = describe_as(monkeypatch, Described(True, "Someone knocking on a door."))
    assert post_detect(client, make_wav(), level_db="-6").json()["kind"] == "none"
    assert calls == [] and store.list_events() == []


def test_enabled_match_wins_over_disabled(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    store.update_sound(add_knock("Knock A", KNOCK), enabled=False)  # the closer one, but disabled
    b = add_knock("Knock B", basis((0, 1.0), (1, 0.3)))
    embed_as(monkeypatch, KNOCK)
    assert post_detect(client, make_wav()).json()["sound_id"] == b


def test_reenabled_sound_matches_again(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    sound_id = add_knock()
    embed_as(monkeypatch, KNOCK)
    store.update_sound(sound_id, enabled=False)
    assert post_detect(client, make_wav()).json()["kind"] == "none"
    store.update_sound(sound_id, enabled=True)
    assert again(client)["sound_id"] == sound_id


def test_closer_to_room_is_not_a_match(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    add_knock()
    embed_as(monkeypatch, basis((0, 1.0), (5, 1.1)))  # above threshold, but nearer the room
    assert post_detect(client, make_wav()).json()["kind"] == "none"


def test_relevant_unknown_is_described(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    add_knock()
    embed_as(monkeypatch, basis((9, 1.0)))
    calls = describe_as(monkeypatch, Described(True, "A kettle whistling on the stove."))
    wav = make_wav()
    body = post_detect(client, wav, level_db="-12.5").json()
    assert set(body) == DETECT_FIELDS
    assert body["kind"] == "unknown"
    assert body["description"] == "A kettle whistling on the stove."
    assert body["label"] is None and body["sound_id"] is None and body["confidence"] is None
    assert calls == [wav]
    [event] = store.list_events()
    assert event["event_id"] == body["event_id"] and event["description"] == body["description"]


def test_background_sound_is_none(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    embed_as(monkeypatch, basis((9, 1.0)))
    describe_as(monkeypatch, Described(False, "Someone typing on a keyboard."))
    body = post_detect(client, make_wav(), level_db="-6").json()
    assert body["kind"] == "none" and body["description"] is None
    assert store.list_events() == []


def test_failed_describe_is_none(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    embed_as(monkeypatch, basis((9, 1.0)))  # describe_relevance hits the offline client and returns None
    body = post_detect(client, make_wav(), level_db="-12.5").json()
    assert body["kind"] == "none"
    assert store.list_events() == []


def test_quiet_unmatched_is_none(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    embed_as(monkeypatch, basis((9, 1.0)))
    monkeypatch.setattr(gemini, "describe_relevance", lambda wav: pytest.fail("should not describe"))
    body = post_detect(client, make_wav(), level_db="-20").json()  # at the cutoff is not loud
    assert body["kind"] == "none"
    assert store.list_events() == []


@pytest.mark.parametrize(
    ("score", "expected"), [(0.6, 0.5), (0.8, 0.75), (1.0, 1.0)], ids=["at_threshold", "mid", "perfect"]
)
def test_taught_confidence(score: float, expected: float) -> None:
    assert detectors.taught_confidence(TaughtScore(score, 0.0, 0.6)) == pytest.approx(expected)


def test_describe_cap_gives_none(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    embed_as(monkeypatch, basis((9, 1.0)))
    calls = describe_as(monkeypatch, Described(True, "A dog barking."))
    first = post_detect(client, make_wav(), level_db="-6").json()
    second = again(client, level_db="-6")
    assert first["kind"] == "unknown" and first["description"] == "A dog barking."
    assert second["kind"] == "none"  # over the cap there is no judgement, so no alert from loudness
    assert len(calls) == 1
    assert len(store.list_events()) == 1


def test_ongoing_sound_is_one_event(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    sound_id = add_knock()
    embed_as(monkeypatch, KNOCK)
    first = post_detect(client, make_wav()).json()
    second = again(client)
    assert second["event_id"] == first["event_id"] and second["sound_id"] == sound_id
    assert set(second) == DETECT_FIELDS
    assert len(store.list_events()) == 1


def test_gap_rearms_the_sound(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    now = [100.0]
    monkeypatch.setattr(ongoing, "events", ongoing.OngoingEvents(clock=lambda: now[0]))
    add_knock()
    embed_as(monkeypatch, KNOCK)
    first = post_detect(client, make_wav()).json()
    now[0] += 9.0
    assert again(client)["event_id"] == first["event_id"]
    now[0] += 9.0  # 9 s after the last detection: still the same ongoing sound
    assert again(client)["event_id"] == first["event_id"]
    now[0] += ongoing.ONGOING_GAP_S
    assert again(client)["event_id"] != first["event_id"]
    assert len(store.list_events()) == 2


def test_different_sounds_are_not_grouped(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    a = add_knock("Knock A", KNOCK)
    b = add_knock("Knock B", basis((3, 1.0)))
    embed_as(monkeypatch, KNOCK)
    post_detect(client, make_wav())
    embed_as(monkeypatch, basis((3, 1.0)))
    assert again(client)["sound_id"] == b
    assert {e["sound_id"] for e in store.list_events()} == {a, b}


def test_detect_log_has_taught_scores_not_names(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    sound_id = add_knock("Grandma's door")
    embed_as(monkeypatch, basis((9, 1.0)))
    describe_as(monkeypatch, Described(True, "A kettle whistling."))
    caplog.set_level(logging.INFO, logger="hear-for-you.detectors")
    post_detect(client, make_wav(), level_db="-6")
    [line] = [r.getMessage() for r in caplog.records if r.getMessage().startswith("detect ")]
    assert f"taught_best={sound_id}:0.000/thr=0.600" in line
    assert "decision=unknown event=new" in line
    assert "Grandma" not in line and "kettle" not in line


@pytest.mark.parametrize(
    ("described", "reason"), [(None, "describe_failed"), (Described(False, "Typing."), "background")]
)
def test_detect_log_says_why_unknown_was_dropped(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    described: Described | None,
    reason: str,
) -> None:
    embed_as(monkeypatch, basis((9, 1.0)))
    describe_as(monkeypatch, described)
    caplog.set_level(logging.INFO, logger="hear-for-you.detectors")
    post_detect(client, make_wav(), level_db="-6")
    ratelimit.detect_limiter.reset()
    post_detect(client, make_wav(), level_db="-6")
    lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith("detect ")]
    assert f"reason={reason}" in lines[0]
    assert "reason=describe_cap" in lines[1]
