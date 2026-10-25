import csv
import logging
from pathlib import Path

import joblib
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app import detectors, gemini, ratelimit, store
from tests.conftest import make_wav
from tests.test_routes import post_detect
from tests.test_teach import basis

ROOT = Path(__file__).resolve().parents[2]
CLASSES = ["builtin_dog_bark", "builtin_siren", "other"]


class FakeClassifier:
    def __init__(self, proba: list[float]) -> None:
        self.proba = np.asarray([proba])

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        assert X.shape == (1, 768)
        return self.proba


def install(monkeypatch: pytest.MonkeyPatch, proba: list[float], classes: list[str] = CLASSES) -> None:
    monkeypatch.setattr(
        detectors, "_builtin", detectors.BuiltinModel(FakeClassifier(proba), classes)
    )
    monkeypatch.setattr(gemini, "embed_audio", lambda wav: basis((9, 1.0)))


def test_builtin_match(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    install(monkeypatch, [0.85, 0.1, 0.05])
    body = post_detect(client, make_wav()).json()
    assert body["kind"] == "builtin"
    assert body["sound_id"] == "builtin_dog_bark" and body["label"] == "Dog bark"
    assert body["confidence"] == 0.85 and body["description"] is None
    [event] = store.list_events()
    assert event["event_id"] == body["event_id"] and event["kind"] == "builtin"


def test_builtin_uses_renamed_label(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    store.update_sound("builtin_siren", name="Ambulance")
    install(monkeypatch, [0.1, 0.8, 0.1])
    assert post_detect(client, make_wav()).json()["label"] == "Ambulance"


@pytest.mark.parametrize(
    "proba", [[0.6, 0.3, 0.1], [0.1, 0.1, 0.8]], ids=["at_threshold", "other_wins"]
)
def test_builtin_no_match(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, proba: list[float]
) -> None:
    install(monkeypatch, proba)
    assert post_detect(client, make_wav()).json()["kind"] == "none"
    assert store.list_events() == []


def test_disabled_builtin_is_not_unknown(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    store.update_sound("builtin_dog_bark", enabled=False)
    install(monkeypatch, [0.9, 0.05, 0.05])
    monkeypatch.setattr(gemini, "describe_relevance", lambda wav: pytest.fail("should not describe"))
    assert post_detect(client, make_wav(), level_db="-6").json()["kind"] == "none"
    assert store.list_events() == []


def test_reenabled_builtin_matches_again(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    install(monkeypatch, [0.9, 0.05, 0.05])
    store.update_sound("builtin_dog_bark", enabled=False)
    assert post_detect(client, make_wav()).json()["kind"] == "none"
    store.update_sound("builtin_dog_bark", enabled=True)
    ratelimit.detect_limiter.reset()
    assert post_detect(client, make_wav()).json()["sound_id"] == "builtin_dog_bark"


def test_taught_beats_builtin(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    vec = basis((9, 1.0))
    sound_id = store.add_sound("Our dog", "dog", vec, np.stack([basis((5, 1.0))]), 0.6)["sound_id"]
    install(monkeypatch, [0.9, 0.05, 0.05])
    body = post_detect(client, make_wav()).json()
    assert body["kind"] == "taught" and body["sound_id"] == sound_id


def test_missing_model_file_turns_builtins_off(tmp_path: Path) -> None:
    detectors.load_builtin(tmp_path / "missing.joblib")
    assert detectors._builtin is None
    assert detectors.match_builtin(basis((0, 1.0))) is None


def test_wrong_embedding_size_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "clf.joblib"
    joblib.dump({"model": None, "classes": CLASSES, "embed_model": "gemini-embedding-2",
                 "dim": 3072, "sklearn_version": "0"}, path)
    with pytest.raises(RuntimeError, match="3072"):
        detectors.load_builtin(path)


def test_committed_model_matches_eval_results() -> None:
    """The shipped model, loaded by the api, makes the same fold-5 decisions eval/ reported."""
    detectors.load_builtin()
    assert detectors._builtin is not None
    with (ROOT / "data/manifests/esc50.csv").open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    X = np.load(ROOT / "data/embeddings/esc50_768.npy")
    index = {row["clip_id"]: i for i, row in enumerate(rows)}
    with (ROOT / "eval/results/builtin_fold5.csv").open(newline="") as handle:
        expected = list(csv.DictReader(handle))
    assert len(expected) == 52
    for row in expected:
        match = detectors.match_builtin(X[index[row["clip_id"]]])
        assert (match[0] if match else "other") == row["predicted"], row["clip_id"]


DISCRETE = ["builtin_door_knock", "builtin_glass_breaking", "other"]


@pytest.mark.parametrize("sound_id", ["builtin_door_knock", "builtin_glass_breaking"])
def test_discrete_sounds_are_never_grouped(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, sound_id: str
) -> None:
    proba = [0.9, 0.05, 0.05] if sound_id == "builtin_door_knock" else [0.05, 0.9, 0.05]
    install(monkeypatch, proba, DISCRETE)
    first = post_detect(client, make_wav()).json()
    ratelimit.detect_limiter.reset()
    second = post_detect(client, make_wav()).json()
    assert first["sound_id"] == second["sound_id"] == sound_id
    assert first["event_id"] != second["event_id"]  # a second knock is a new alert
    assert len(store.list_events()) == 2


def test_sustained_sounds_are_still_grouped(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    install(monkeypatch, [0.9, 0.05, 0.05])  # dog bark
    first = post_detect(client, make_wav()).json()
    ratelimit.detect_limiter.reset()
    assert post_detect(client, make_wav()).json()["event_id"] == first["event_id"]
    assert len(store.list_events()) == 1


def test_detect_logs_scores_and_reason(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    store.update_sound("builtin_siren", name="Private name")
    install(monkeypatch, [0.3, 0.55, 0.15])  # siren on top, below the 0.6 gate
    caplog.set_level(logging.INFO, logger="hear-for-you.detectors")
    post_detect(client, make_wav(), level_db="-30")
    [line] = [r.getMessage() for r in caplog.records if r.getMessage().startswith("detect ")]
    assert "builtin_top=builtin_siren:0.550,builtin_dog_bark:0.300" in line
    assert "decision=none" in line and "reason=quiet" in line and "smoke=no" in line
    assert "Private name" not in line


def test_detect_log_says_grouped_and_disabled(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    install(monkeypatch, [0.9, 0.05, 0.05])
    caplog.set_level(logging.INFO, logger="hear-for-you.detectors")
    post_detect(client, make_wav())
    ratelimit.detect_limiter.reset()
    post_detect(client, make_wav())
    store.update_sound("builtin_dog_bark", enabled=False)
    ratelimit.detect_limiter.reset()
    post_detect(client, make_wav(), level_db="-6")
    lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith("detect ")]
    assert "decision=builtin:builtin_dog_bark event=new" in lines[0]
    assert "event=grouped" in lines[1]
    assert "reason=disabled:builtin_dog_bark" in lines[2]


def test_detect_log_on_rate_limit(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    install(monkeypatch, [0.9, 0.05, 0.05])
    caplog.set_level(logging.INFO, logger="hear-for-you.detectors")
    post_detect(client, make_wav())
    assert post_detect(client, make_wav()).status_code == 429
    lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith("detect ")]
    assert "decision=error reason=rate_limited" in lines[1]
