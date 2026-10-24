"""SQLite storage: sounds, their embedding vectors (as BLOB), and alert history. Never audio."""

import secrets
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime

import numpy as np

from app.config import settings
from app.errors import BadRequest, NotFound

ICONS = frozenset({
    "door", "bell", "alarm", "baby", "dog", "kettle", "microwave",
    "phone", "voice", "glass", "siren", "water", "generic",
})

# (sound_id, name, icon), in contract order.
BUILTINS = [
    ("builtin_smoke_alarm", "Smoke alarm", "alarm"),
    ("builtin_crying_baby", "Crying baby", "baby"),
    ("builtin_dog_bark", "Dog bark", "dog"),
    ("builtin_door_knock", "Door knock", "door"),
    ("builtin_glass_breaking", "Glass breaking", "glass"),
    ("builtin_siren", "Siren", "siren"),
]

EVENT_KINDS = frozenset({"builtin", "taught", "unknown"})

SCHEMA = """
CREATE TABLE IF NOT EXISTS sounds (
    sound_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    icon TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('builtin', 'taught')),
    enabled INTEGER NOT NULL DEFAULT 1,
    threshold REAL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS vectors (
    sound_id TEXT NOT NULL REFERENCES sounds (sound_id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('prototype', 'room')),
    idx INTEGER NOT NULL,
    vector BLOB NOT NULL,
    PRIMARY KEY (sound_id, role, idx)
);
CREATE TABLE IF NOT EXISTS history (
    event_id TEXT PRIMARY KEY,
    at TEXT NOT NULL,
    kind TEXT NOT NULL,
    label TEXT,
    sound_id TEXT,
    confidence REAL,
    description TEXT
);
CREATE INDEX IF NOT EXISTS history_at ON history (at);
"""


@dataclass(frozen=True)
class TaughtModel:
    sound_id: str
    name: str
    prototype: np.ndarray  # (EMBED_DIM,), unit length
    room: np.ndarray  # (n_room, EMBED_DIM), each row unit length
    threshold: float


def parse_time(value: str) -> str:
    """Any ISO 8601 time -> the stored UTC format. Naive times are taken as UTC."""
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise BadRequest(f"Invalid ISO 8601 time: {value}.") from None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_id(prefix: str) -> str:
    """Short random id, e.g. snd_1a2b3c4d. 8 hex chars so history ids don't collide in practice."""
    return f"{prefix}_{secrets.token_hex(4)}"


def utc_now() -> str:
    """ISO 8601 UTC to the second, e.g. 2026-10-24T14:02:11Z. Sorts correctly as a string."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


@contextmanager
def _connect(db_path: str | None) -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(db_path or settings.db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        with conn:  # commits on success, rolls back on error
            yield conn
    finally:
        conn.close()


def _to_blob(vector: np.ndarray) -> bytes:
    vec = np.asarray(vector, dtype=np.float32)
    if vec.shape != (settings.embed_dim,):
        raise ValueError(f"Vector must have shape ({settings.embed_dim},), got {vec.shape}.")
    norm = float(np.linalg.norm(vec))
    if not np.isfinite(norm) or norm == 0.0:
        raise ValueError("Vector must be finite and non-zero.")
    return (vec / norm).astype(np.float32).tobytes()


def _from_blob(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32)


def _clean_name(name: str) -> str:
    cleaned = name.strip()
    if not 1 <= len(cleaned) <= 40:
        raise BadRequest("Name must be 1 to 40 characters.")
    return cleaned


def _sound_dict(row: sqlite3.Row) -> dict[str, object]:
    return {
        "sound_id": row["sound_id"],
        "name": row["name"],
        "icon": row["icon"],
        "kind": row["kind"],
        "enabled": bool(row["enabled"]),
    }


def _event_dict(row: sqlite3.Row) -> dict[str, object]:
    return {
        "event_id": row["event_id"],
        "at": row["at"],
        "kind": row["kind"],
        "label": row["label"],
        "sound_id": row["sound_id"],
        "confidence": row["confidence"],
        "description": row["description"],
    }


def init_db(db_path: str | None = None) -> None:
    """Create tables if missing and seed the built-ins. Safe to call on every startup."""
    now = utc_now()
    with _connect(db_path) as conn:
        conn.executescript(SCHEMA)
        conn.executemany(
            "INSERT OR IGNORE INTO sounds (sound_id, name, icon, kind, enabled, threshold, created_at)"
            " VALUES (?, ?, ?, 'builtin', 1, NULL, ?)",
            [(sound_id, name, icon, now) for sound_id, name, icon in BUILTINS],
        )


def add_sound(
    name: str,
    icon: str,
    prototype: np.ndarray,
    room: np.ndarray,
    threshold: float,
    db_path: str | None = None,
) -> dict[str, object]:
    """Save a taught sound with its prototype vector and room vectors (one per row of `room`)."""
    name = _clean_name(name)
    if icon not in ICONS:
        raise BadRequest(f"Unknown icon: {icon}.")
    proto_blob = _to_blob(prototype)
    room_blobs = [_to_blob(row) for row in np.atleast_2d(room)]
    sound_id = new_id("snd")
    with _connect(db_path) as conn:
        conn.execute(
            "INSERT INTO sounds (sound_id, name, icon, kind, enabled, threshold, created_at)"
            " VALUES (?, ?, ?, 'taught', 1, ?, ?)",
            (sound_id, name, icon, float(threshold), utc_now()),
        )
        conn.execute(
            "INSERT INTO vectors (sound_id, role, idx, vector) VALUES (?, 'prototype', 0, ?)",
            (sound_id, proto_blob),
        )
        conn.executemany(
            "INSERT INTO vectors (sound_id, role, idx, vector) VALUES (?, 'room', ?, ?)",
            [(sound_id, i, blob) for i, blob in enumerate(room_blobs)],
        )
    return get_sound(sound_id, db_path)


def get_sound(sound_id: str, db_path: str | None = None) -> dict[str, object]:
    with _connect(db_path) as conn:
        row = conn.execute("SELECT * FROM sounds WHERE sound_id = ?", (sound_id,)).fetchone()
    if row is None:
        raise NotFound(f"Unknown sound_id: {sound_id}.")
    return _sound_dict(row)


def list_sounds(db_path: str | None = None) -> list[dict[str, object]]:
    """Built-ins first (contract order), then taught sounds oldest first."""
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM sounds ORDER BY kind = 'taught', created_at, rowid"
        ).fetchall()
    return [_sound_dict(row) for row in rows]


def update_sound(
    sound_id: str,
    enabled: bool | None = None,
    name: str | None = None,
    db_path: str | None = None,
) -> dict[str, object]:
    """Toggle and/or rename any sound, built-ins included."""
    get_sound(sound_id, db_path)  # raises NotFound
    with _connect(db_path) as conn:
        if enabled is not None:
            conn.execute(
                "UPDATE sounds SET enabled = ? WHERE sound_id = ?", (int(enabled), sound_id)
            )
        if name is not None:
            conn.execute(
                "UPDATE sounds SET name = ? WHERE sound_id = ?", (_clean_name(name), sound_id)
            )
    return get_sound(sound_id, db_path)


def delete_sound(sound_id: str, db_path: str | None = None) -> None:
    """Delete a taught sound and its vectors. Built-ins can only be disabled."""
    sound = get_sound(sound_id, db_path)  # raises NotFound
    if sound["kind"] == "builtin":
        raise BadRequest("Built-in sounds cannot be deleted. Disable them instead.")
    with _connect(db_path) as conn:
        conn.execute("DELETE FROM sounds WHERE sound_id = ?", (sound_id,))


def taught_models(db_path: str | None = None) -> list[TaughtModel]:
    """Every enabled taught sound with its vectors, for the detectors."""
    with _connect(db_path) as conn:
        sounds = conn.execute(
            "SELECT sound_id, name, threshold FROM sounds"
            " WHERE kind = 'taught' AND enabled = 1 ORDER BY created_at, rowid"
        ).fetchall()
        vectors = conn.execute(
            "SELECT v.sound_id, v.role, v.vector FROM vectors v"
            " JOIN sounds s ON s.sound_id = v.sound_id"
            " WHERE s.kind = 'taught' AND s.enabled = 1 ORDER BY v.sound_id, v.role, v.idx"
        ).fetchall()
    protos: dict[str, np.ndarray] = {}
    rooms: dict[str, list[np.ndarray]] = {row["sound_id"]: [] for row in sounds}
    for row in vectors:
        vec = _from_blob(row["vector"])
        if row["role"] == "prototype":
            protos[row["sound_id"]] = vec
        else:
            rooms[row["sound_id"]].append(vec)
    empty_room = np.empty((0, settings.embed_dim), dtype=np.float32)
    return [
        TaughtModel(
            sound_id=row["sound_id"],
            name=row["name"],
            prototype=protos[row["sound_id"]],
            room=np.stack(rooms[row["sound_id"]]) if rooms[row["sound_id"]] else empty_room,
            threshold=float(row["threshold"]),
        )
        for row in sounds
    ]


def add_event(
    kind: str,
    label: str | None,
    sound_id: str | None,
    confidence: float | None,
    description: str | None,
    db_path: str | None = None,
) -> dict[str, object]:
    """Save a detect result to history. "none" results are never saved."""
    if kind not in EVENT_KINDS:
        raise ValueError(f"Cannot save event of kind {kind!r}.")
    event_id = new_id("evt")
    with _connect(db_path) as conn:
        conn.execute(
            "INSERT INTO history (event_id, at, kind, label, sound_id, confidence, description)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (event_id, utc_now(), kind, label, sound_id, confidence, description),
        )
        row = conn.execute("SELECT * FROM history WHERE event_id = ?", (event_id,)).fetchone()
    return _event_dict(row)


def list_events(
    since: str | None = None, limit: int = 100, db_path: str | None = None
) -> list[dict[str, object]]:
    """Newest first. `since` keeps events at or after that time (callers dedupe by event_id)."""
    if since is not None:
        since = parse_time(since)
    with _connect(db_path) as conn:
        if since is None:
            rows = conn.execute(
                "SELECT * FROM history ORDER BY at DESC, rowid DESC LIMIT ?", (limit,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM history WHERE at >= ? ORDER BY at DESC, rowid DESC LIMIT ?",
                (since, limit),
            ).fetchall()
    return [_event_dict(row) for row in rows]
