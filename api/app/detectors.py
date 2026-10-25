"""Detectors. The taught-sound match rule lives here so /teach's self-check and /detect agree.

/detect decision order (api/AGENTS.md): smoke-alarm rule -> taught match -> built-in classifier
-> loud unknown judged relevant -> none. A disabled sound that matches makes the clip "none" instead of
"unknown", unless an enabled sound also matches.
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import joblib
import numpy as np
import sklearn

from app import gemini, ongoing, ratelimit, smoke_alarm, store
from app.config import settings
from app.errors import ApiError

log = logging.getLogger("hear-for-you.detectors")

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
    """The taught sound with the highest score among those that match, if any."""
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


def builtin_ranking(vec: np.ndarray) -> list[tuple[str, float]]:
    """Every class with its calibrated probability, highest first. Empty without the classifier."""
    if _builtin is None:
        return []
    proba = _builtin.classifier.predict_proba(vec.reshape(1, -1))[0]
    return sorted(zip(_builtin.classes, map(float, proba)), key=lambda pair: -pair[1])


def accept_builtin(ranking: list[tuple[str, float]]) -> tuple[str, float] | None:
    """The top class if it is a built-in sound above BUILTIN_MIN_PROB, else None."""
    if not ranking:
        return None
    label, p = ranking[0]
    if label == OTHER or p <= BUILTIN_MIN_PROB:
        return None
    return label, p


def match_builtin(vec: np.ndarray) -> tuple[str, float] | None:
    return accept_builtin(builtin_ranking(vec))


Trace = dict[str, object]


def _admit(
    trace: Trace,
    kind: str,
    label: str | None,
    sound_id: str | None,
    confidence: float | None,
    description: str | None,
) -> dict[str, object]:
    """Save a new history event, or return the open one if this sound is still ongoing."""
    def save() -> dict[str, object]:
        return store.add_event(kind, label, sound_id, confidence, description)

    event, grouped = ongoing.events.admit(sound_id or "unknown", confidence, save)
    trace["decision"] = f"{kind}:{sound_id}" if sound_id else kind
    trace["event"] = "grouped" if grouped else "new"
    return event


def _none(trace: Trace, reason: str) -> dict[str, object]:
    trace["decision"] = "none"
    trace["reason"] = reason
    return {
        "event_id": store.new_id("evt"),
        "kind": "none",
        "label": None,
        "sound_id": None,
        "confidence": None,
        "description": None,
    }


def _format(trace: Trace) -> str:
    return " ".join(
        f"{key}={value:.3f}" if isinstance(value, float) else f"{key}={value}" for key, value in trace.items()
    )


def detect(wav: bytes, samples: np.ndarray, level_db: float) -> dict[str, object]:
    """Run one validated clip through the detectors. Saves new non-"none" events to history.

    Logs one "detect ..." line per clip with the scores and the reason for the decision: sound IDs and
    numbers only, never audio, embeddings, descriptions or sound names.
    """
    trace: Trace = {"level_db": round(level_db, 1)}
    try:
        return _detect(wav, samples, level_db, trace)
    except ApiError as exc:
        trace["decision"] = "error"
        trace["reason"] = exc.code
        raise
    finally:
        log.info("detect %s", _format(trace))


def _detect(wav: bytes, samples: np.ndarray, level_db: float, trace: Trace) -> dict[str, object]:
    """The smoke-alarm rule runs first, on the raw samples: no embedding, so it is never rate-limited and
    still works when Gemini is down. Everything after it costs a Gemini call and is rate-limited.
    """
    suppressed: list[str] = []  # disabled sounds that matched: never relabel the clip as unknown
    alarm = smoke_alarm.detect(samples)
    trace["smoke"] = f"{alarm.score:.2f}" if alarm.detected else "no"
    if alarm.detected:
        sound = store.get_sound(SMOKE_ALARM_ID)
        if sound["enabled"]:
            return _admit(trace, "builtin", str(sound["name"]), SMOKE_ALARM_ID, alarm.score, None)
        suppressed.append(SMOKE_ALARM_ID)  # keep going: an enabled sound may be sounding at the same time

    ratelimit.detect_limiter.check()
    vec = gemini.embed_audio(wav)

    models = store.taught_models(include_disabled=True)
    if models:
        scored = [(m, score_taught(vec, m.prototype, m.room, m.threshold)) for m in models]
        best_model, best = max(scored, key=lambda pair: pair[1].score)
        trace["taught_best"] = (
            f"{best_model.sound_id}:{best.score:.3f}/thr={best.threshold:.3f}/room={best.room_score:.3f}"
        )
    match = match_taught(vec, [m for m in models if m.enabled])
    if match is not None:
        model, result = match
        return _admit(trace, "taught", model.name, model.sound_id, taught_confidence(result), None)
    disabled = match_taught(vec, [m for m in models if not m.enabled])
    if disabled is not None:
        suppressed.append(disabled[0].sound_id)

    ranking = builtin_ranking(vec)
    if ranking:
        trace["builtin_top"] = ",".join(f"{label}:{p:.3f}" for label, p in ranking[:2])
    builtin = accept_builtin(ranking)
    if builtin is not None:
        sound_id, p = builtin
        sound = store.get_sound(sound_id)
        if sound["enabled"]:
            return _admit(trace, "builtin", str(sound["name"]), sound_id, round(p, 2), None)
        suppressed.append(sound_id)

    if suppressed:
        return _none(trace, "disabled:" + ",".join(suppressed))
    if level_db <= LOUD_DBFS:
        return _none(trace, "quiet")
    if not ratelimit.describe_limiter.allow():
        return _none(trace, "describe_cap")
    # Loudness alone never makes an alert: the describe model must judge the sound relevant.
    described = gemini.describe_relevance(wav)
    if described is None:
        return _none(trace, "describe_failed")
    if not described.relevant:
        return _none(trace, "background")
    return _admit(trace, "unknown", None, None, None, described.description)
