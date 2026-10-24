"""Detectors. The taught-sound match rule lives here so /teach's self-check and /detect agree."""

from dataclasses import dataclass

import numpy as np


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
