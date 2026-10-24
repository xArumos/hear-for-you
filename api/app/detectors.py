"""Detectors. The taught-sound match rule lives here so /teach's self-check and /detect agree.

/detect decision order (api/AGENTS.md): smoke-alarm rule -> taught match -> built-in classifier
-> loud unknown -> none.
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import joblib
import numpy as np
import sklearn

from app import gemini, ratelimit, smoke_alarm, store
from app.config import settings

log = logging.getLogger("hearalert.detectors")

LOUD_DBFS = -20.0
BUILTIN_MIN_PROB = 0.6
SMOKE_ALARM_ID = "builtin_smoke_alarm"
BUILTIN_MODEL_PATH = Path(__file__).resolve().parent.parent / "models" / "builtin_clf.joblib"
OTHER = "other"


class Classifier(Protocol):
    def predict_proba(self, X: np.ndarray) -> np.ndarray: ...


@dataclass(frozen=True)
class BuiltinModel:
    classifier: Classifier
    classes: list[str]  # "other" or a builtin_ sound_id, in predict_proba column order


_builtin: BuiltinModel | None = None


@dataclass(frozen=True)
class TaughtScore:
    score: float  # cosine to the sound's prototype
    room_score: float  # highest cosine to any of its room vectors
    threshold: float

    @property
    def matched(self) -> bool:
        return self.score >= self.threshold and self.score > self.room_score


def unit(vector: np.ndarray) -> np.ndarray:
    vec = np.asarray(vector, dtype=np.float32)
    return vec / float(np.linalg.norm(vec))


def score_taught(
    vec: np.ndarray, prototype: np.ndarray, room: np.ndarray, threshold: float
) -> TaughtScore:
    """Score a unit vector against one taught sound. A match must beat the threshold and the room."""
    room_score = float(np.max(room @ vec)) if len(room) else -1.0
    return TaughtScore(float(prototype @ vec), room_score, threshold)


def taught_confidence(result: TaughtScore) -> float:
    """Map a match onto [0.5, 1]: 0.5 at the threshold, 1.0 at a perfect cosine."""
    headroom = max(1.0 - result.threshold, 1e-6)
    return round(min(1.0, 0.5 + 0.5 * (result.score - result.threshold) / headroom), 2)


def match_taught(
    vec: np.ndarray, models: list[store.TaughtModel]
) -> tuple[store.TaughtModel, TaughtScore] | None:
    """The enabled taught sound with the highest score among those that match, if any."""
    best: tuple[store.TaughtModel, TaughtScore] | None = None
    for model in models:
        result = score_taught(vec, model.prototype, model.room, model.threshold)
        if result.matched and (best is None or result.score > best[1].score):
            best = (model, result)
    return best


def load_builtin(path: Path = BUILTIN_MODEL_PATH) -> None:
    """Load the classifier trained by eval/train_builtin.py. Without it, /detect skips the built-in step."""
    global _builtin
    if not path.is_file():
        log.warning("no built-in classifier at %s; built-in sounds are off", path.name)
        _builtin = None
        return
    bundle = joblib.load(path)  # our own committed file, written by eval/train_builtin.py
    if bundle["dim"] != settings.embed_dim or bundle["embed_model"] != settings.embed_model:
        raise RuntimeError(
            f"{path.name} was trained on {bundle['embed_model']}/{bundle['dim']}; retrain it."
        )
    if bundle["sklearn_version"] != sklearn.__version__:
        log.warning(
            "built-in classifier saved with scikit-learn %s, running %s; retrain if results look off",
            bundle["sklearn_version"], sklearn.__version__,
        )
    _builtin = BuiltinModel(bundle["model"], list(bundle["classes"]))
    log.info("loaded built-in classifier: %s", ", ".join(_builtin.classes))


def match_builtin(vec: np.ndarray) -> tuple[str, float] | None:
    """The top class if it is a built-in sound above BUILTIN_MIN_PROB, else None."""
    if _builtin is None:
        return None
    proba = _builtin.classifier.predict_proba(vec.reshape(1, -1))[0]
    top = int(np.argmax(proba))
    label, p = _builtin.classes[top], float(proba[top])
    if label == OTHER or p <= BUILTIN_MIN_PROB:
        return None
    return label, p


def detect(wav: bytes, samples: np.ndarray, level_db: float) -> dict[str, object]:
    """Run one validated clip through the detectors. Saves every result except "none" to history.

    The smoke-alarm rule runs first, on the raw samples: no embedding, so it is never rate-limited and
    still works when Gemini is down. Everything after it costs a Gemini call and is rate-limited.
    """
    alarm = smoke_alarm.detect(samples)
    if alarm.detected:
        sound = store.get_sound(SMOKE_ALARM_ID)
        if sound["enabled"]:
            return store.add_event("builtin", str(sound["name"]), SMOKE_ALARM_ID, alarm.score, None)

    ratelimit.detect_limiter.check()
    vec = gemini.embed_audio(wav)

    match = match_taught(vec, store.taught_models())
    if match is not None:
        model, result = match
        return store.add_event(
            "taught", model.name, model.sound_id, taught_confidence(result), None
        )

    builtin = match_builtin(vec)
    if builtin is not None:
        sound_id, p = builtin
        sound = store.get_sound(sound_id)
        if sound["enabled"]:
            return store.add_event("builtin", str(sound["name"]), sound_id, round(p, 2), None)

    if level_db > LOUD_DBFS:
        # Over the describe cap the sound is still "unknown", just without a description.
        description = gemini.describe_audio(wav) if ratelimit.describe_limiter.allow() else None
        return store.add_event("unknown", None, None, None, description)

    return {
        "event_id": store.new_id("evt"),
        "kind": "none",
        "label": None,
        "sound_id": None,
        "confidence": None,
        "description": None,
    }
