"""Detectors. The taught-sound match rule lives here so /teach's self-check and /detect agree.

/detect decision order (api/AGENTS.md): taught match -> built-in classifier -> loud unknown -> none.
"""

from dataclasses import dataclass

import numpy as np

from app import gemini, store

LOUD_DBFS = -20.0


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


def detect(wav: bytes, level_db: float) -> dict[str, object]:
    """Run one validated clip through the detectors. Saves every result except "none" to history."""
    vec = gemini.embed_audio(wav)

    match = match_taught(vec, store.taught_models())
    if match is not None:
        model, result = match
        return store.add_event(
            "taught", model.name, model.sound_id, taught_confidence(result), None
        )

    # Built-in classifier goes here once eval/ has trained it (needs P3's ESC-50 embeddings).

    if level_db > LOUD_DBFS:
        return store.add_event("unknown", None, None, None, gemini.describe_audio(wav))

    return {
        "event_id": store.new_id("evt"),
        "kind": "none",
        "label": None,
        "sound_id": None,
        "confidence": None,
        "description": None,
    }
