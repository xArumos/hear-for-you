"""Teach a sound: embed 3 examples + 3 room windows, build a prototype, self-check example 3."""

from concurrent.futures import ThreadPoolExecutor

import numpy as np

from app import audio, gemini, store
from app.audio import ROOM_SECONDS
from app.detectors import score_taught, unit

# Threshold sits this far from the room's best score toward the examples' score (0.5 = midpoint).
THRESHOLD_MIX = 0.5


def teach(
    name: str, icon: str, examples: list[bytes], room_wav: bytes
) -> dict[str, object]:
    """Validate everything first (no Gemini calls on bad input), then embed and save.

    Prototype = normalized mean of examples 1 and 2. Threshold = between cos(ex1, ex2) and the room's
    best cosine to the prototype. Example 3 is held out and checked with the same rule /detect uses.
    The sound is saved even if the self-check fails; the frontend asks the user to re-record.
    """
    name = store.clean_name(name)
    store.check_icon(icon)
    for wav in examples:
        audio.validate_clip(wav)
    room_samples = audio.validate_clip(room_wav, seconds=ROOM_SECONDS, allow_silent=True)
    clips = [*examples, *audio.room_windows(room_samples)]

    with ThreadPoolExecutor(max_workers=len(clips)) as pool:
        vectors = list(pool.map(gemini.embed_audio, clips))
    ex1, ex2, ex3 = vectors[:3]
    room = np.stack(vectors[3:])

    prototype = unit(ex1 + ex2)
    positive = float(ex1 @ ex2)
    negative = float(np.max(room @ prototype))
    threshold = negative + THRESHOLD_MIX * (positive - negative)
    check = score_taught(ex3, prototype, room, threshold)

    sound = store.add_sound(name, icon, prototype, room, threshold)
    return {
        "sound_id": sound["sound_id"],
        "name": sound["name"],
        "icon": sound["icon"],
        "self_check": {
            "passed": check.matched,
            "score": round(check.score, 3),
            "threshold": round(threshold, 3),
        },
    }
