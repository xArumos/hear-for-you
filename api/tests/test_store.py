import sqlite3
from pathlib import Path

import numpy as np
import pytest

from app import store
from app.errors import BadRequest, NotFound

DIM = 768


@pytest.fixture
def db(tmp_path: Path) -> str:
    path = str(tmp_path / "test.db")
    store.init_db(path)
    return path


def vec(seed: int) -> np.ndarray:
    return np.random.default_rng(seed).normal(size=DIM).astype(np.float32) * 3.0


def add_knock(db: str, name: str = "Door knock") -> dict[str, object]:
    room = np.stack([vec(10), vec(11), vec(12)])
    return store.add_sound(name, "door", vec(1), room, 0.71, db_path=db)


def count(db: str, sql: str) -> int:
    with sqlite3.connect(db) as conn:
        return int(conn.execute(sql).fetchone()[0])


def test_init_twice_seeds_six_builtins(db: str) -> None:
    store.init_db(db)
    sounds = store.list_sounds(db)
    assert [s["sound_id"] for s in sounds] == [b[0] for b in store.BUILTINS]
    assert all(s["kind"] == "builtin" and s["enabled"] is True for s in sounds)


def test_init_keeps_user_changes_to_builtins(db: str) -> None:
    store.update_sound("builtin_siren", enabled=False, name="Ambulance", db_path=db)
    store.init_db(db)
    assert store.get_sound("builtin_siren", db) == {
        "sound_id": "builtin_siren", "name": "Ambulance", "icon": "siren",
        "kind": "builtin", "enabled": False,
    }


def test_add_get_list_round_trip(db: str) -> None:
    sound = add_knock(db, name="  Door knock  ")
    assert sound["sound_id"].startswith("snd_") and len(sound["sound_id"]) == 12
    assert sound == {
        "sound_id": sound["sound_id"], "name": "Door knock", "icon": "door",
        "kind": "taught", "enabled": True,
    }
    assert store.get_sound(sound["sound_id"], db) == sound
    assert store.list_sounds(db)[-1] == sound


def test_taught_sounds_listed_after_builtins_oldest_first(db: str) -> None:
    first = add_knock(db, "First")
    second = add_knock(db, "Second")
    ids = [s["sound_id"] for s in store.list_sounds(db)]
    assert ids[6:] == [first["sound_id"], second["sound_id"]]


@pytest.mark.parametrize("name", ["", "   ", "x" * 41])
def test_add_rejects_bad_name(db: str, name: str) -> None:
    with pytest.raises(BadRequest):
        add_knock(db, name=name)


def test_add_rejects_bad_icon(db: str) -> None:
    with pytest.raises(BadRequest):
        store.add_sound("Kettle", "teapot", vec(1), vec(2), 0.7, db_path=db)


def test_add_rejects_wrong_dim(db: str) -> None:
    with pytest.raises(ValueError):
        store.add_sound("Kettle", "kettle", np.ones(512), vec(2), 0.7, db_path=db)
    with pytest.raises(ValueError):
        store.add_sound("Kettle", "kettle", np.zeros(DIM), vec(2), 0.7, db_path=db)
    assert count(db, "SELECT COUNT(*) FROM sounds WHERE kind = 'taught'") == 0


def test_taught_models_vectors_unit_length(db: str) -> None:
    sound = add_knock(db)
    [model] = store.taught_models(db)
    assert model.sound_id == sound["sound_id"] and model.name == "Door knock"
    assert model.threshold == pytest.approx(0.71)
    assert model.prototype.shape == (DIM,)
    assert model.room.shape == (3, DIM)
    assert np.linalg.norm(model.prototype) == pytest.approx(1.0, abs=1e-5)
    assert np.allclose(np.linalg.norm(model.room, axis=1), 1.0, atol=1e-5)
    expected = vec(1) / np.linalg.norm(vec(1))
    assert np.allclose(model.prototype, expected, atol=1e-6)


def test_taught_models_skips_disabled(db: str) -> None:
    keep = add_knock(db, "Keep")
    off = add_knock(db, "Off")
    store.update_sound(str(off["sound_id"]), enabled=False, db_path=db)
    assert [m.sound_id for m in store.taught_models(db)] == [keep["sound_id"]]
    every = store.taught_models(db, include_disabled=True)
    assert [(m.sound_id, m.enabled) for m in every] == [(keep["sound_id"], True), (off["sound_id"], False)]
    assert all(len(m.room) for m in every)


def test_update_taught_sound(db: str) -> None:
    sound_id = str(add_knock(db)["sound_id"])
    updated = store.update_sound(sound_id, enabled=False, name="Front door", db_path=db)
    assert updated["enabled"] is False and updated["name"] == "Front door"
    with pytest.raises(BadRequest):
        store.update_sound(sound_id, name="", db_path=db)


def test_delete_taught_removes_vectors(db: str) -> None:
    sound_id = str(add_knock(db)["sound_id"])
    assert count(db, "SELECT COUNT(*) FROM vectors") == 4
    store.delete_sound(sound_id, db)
    assert count(db, "SELECT COUNT(*) FROM vectors") == 0
    with pytest.raises(NotFound):
        store.get_sound(sound_id, db)


def test_delete_builtin_rejected(db: str) -> None:
    with pytest.raises(BadRequest):
        store.delete_sound("builtin_dog_bark", db)
    assert store.get_sound("builtin_dog_bark", db)["kind"] == "builtin"


def test_unknown_sound_id(db: str) -> None:
    with pytest.raises(NotFound):
        store.get_sound("snd_nope", db)
    with pytest.raises(NotFound):
        store.update_sound("snd_nope", enabled=False, db_path=db)
    with pytest.raises(NotFound):
        store.delete_sound("snd_nope", db)


def test_add_event_shape(db: str) -> None:
    event = store.add_event("taught", "Door knock", "snd_1234abcd", 0.94, None, db_path=db)
    assert set(event) == {
        "event_id", "at", "kind", "label", "sound_id", "confidence", "description",
    }
    assert str(event["event_id"]).startswith("evt_")
    assert str(event["at"]).endswith("Z") and len(str(event["at"])) == 20


def test_add_event_rejects_none(db: str) -> None:
    with pytest.raises(ValueError):
        store.add_event("none", None, None, None, None, db_path=db)


def test_list_events_order_since_limit(db: str, monkeypatch: pytest.MonkeyPatch) -> None:
    times = iter(["2026-10-24T14:00:00Z", "2026-10-24T14:01:00Z", "2026-10-24T14:01:00Z"])
    monkeypatch.setattr(store, "utc_now", lambda: next(times))
    a = store.add_event("builtin", "Siren", "builtin_siren", 0.8, None, db_path=db)
    b = store.add_event("unknown", None, None, None, "A kettle whistling.", db_path=db)
    c = store.add_event("taught", "Door knock", "snd_1234abcd", 0.9, None, db_path=db)

    assert [e["event_id"] for e in store.list_events(db_path=db)] == [
        c["event_id"], b["event_id"], a["event_id"],
    ]
    assert [e["event_id"] for e in store.list_events(limit=1, db_path=db)] == [c["event_id"]]
    since = store.list_events(since="2026-10-24T14:01:00Z", db_path=db)
    assert [e["event_id"] for e in since] == [c["event_id"], b["event_id"]]
    assert store.list_events(since="2026-10-24T15:00:00Z", db_path=db) == []
