from dataclasses import dataclass, field

import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app import audio, gemini, store
from tests.conftest import make_wav
from tests.test_routes import assert_error_shape

EX = [make_wav(amplitude=a) for a in (0.5, 0.4, 0.3)]
ROOM = make_wav(seconds=10.0, amplitude=0.05)


def basis(*weights: tuple[int, float]) -> np.ndarray:
    vec = np.zeros(768, dtype=np.float32)
    for i, w in weights:
        vec[i] = w
    return vec / np.linalg.norm(vec)


@dataclass
class FakeEmbed:
    """Examples map to the vectors a test sets; anything else (the room windows) is the "room" vector."""

    vectors: dict[bytes, np.ndarray] = field(default_factory=dict)
    calls: list[bytes] = field(default_factory=list)

    def __call__(self, wav: bytes) -> np.ndarray:
        self.calls.append(wav)
        return self.vectors.get(wav, basis((5, 1.0)))

    def set_examples(self, *vectors: np.ndarray) -> None:
        self.vectors.update(zip(EX, vectors))


@pytest.fixture
def fake_embed(monkeypatch: pytest.MonkeyPatch) -> FakeEmbed:
    fake = FakeEmbed()
    monkeypatch.setattr(gemini, "embed_audio", fake)
    return fake


def post_teach(
    client: TestClient,
    name: str = "Kettle",
    icon: str | None = "kettle",
    examples: list[bytes] = EX,
    room: bytes = ROOM,
) -> httpx.Response:
    data = {"name": name}
    if icon is not None:
        data["icon"] = icon
    files = {f"example_{i + 1}": (f"ex{i + 1}.wav", wav, "audio/wav") for i, wav in enumerate(examples)}
    files["room"] = ("room.wav", room, "audio/wav")
    return client.post("/api/teach", data=data, files=files)


def test_teach_passes_self_check(client: TestClient, fake_embed: FakeEmbed) -> None:
    fake_embed.set_examples(
        basis((0, 1.0), (1, 0.2)),
        basis((0, 1.0), (2, 0.2)),
        basis((0, 1.0), (3, 0.2)),
    )
    res = post_teach(client)
    assert res.status_code == 200
    body = res.json()
    assert set(body) == {"sound_id", "name", "icon", "self_check", "latency_ms"}
    assert body["sound_id"].startswith("snd_")
    assert body["name"] == "Kettle" and body["icon"] == "kettle"
    check = body["self_check"]
    assert check["passed"] is True
    assert check["score"] > check["threshold"] > 0
    assert len(fake_embed.calls) == 6

    sounds = client.get("/api/sounds").json()["sounds"]
    assert sounds[-1]["sound_id"] == body["sound_id"] and sounds[-1]["kind"] == "taught"
    [model] = store.taught_models()
    assert model.room.shape == (3, 768)
    assert model.threshold == pytest.approx(check["threshold"], abs=1e-3)


def test_teach_failed_self_check_still_saves(
    client: TestClient, fake_embed: FakeEmbed
) -> None:
    fake_embed.set_examples(
        basis((0, 1.0), (1, 0.2)),
        basis((0, 1.0), (2, 0.2)),
        basis((6, 1.0)),
    )
    res = post_teach(client)
    assert res.status_code == 200
    assert res.json()["self_check"]["passed"] is False
    assert len(store.taught_models()) == 1


def test_teach_example_closer_to_room_fails(
    client: TestClient, fake_embed: FakeEmbed
) -> None:
    fake_embed.set_examples(
        basis((0, 1.0), (1, 0.2)),
        basis((0, 1.0), (2, 0.2)),
        basis((0, 1.0), (5, 1.2)),  # near the prototype, but nearer the room
    )
    assert post_teach(client).json()["self_check"]["passed"] is False


def test_teach_icon_defaults_to_generic(
    client: TestClient, fake_embed: FakeEmbed
) -> None:
    res = post_teach(client, icon=None)
    assert res.status_code == 200
    assert res.json()["icon"] == "generic"


def test_teach_quiet_room_is_allowed(
    client: TestClient, fake_embed: FakeEmbed
) -> None:
    assert post_teach(client, room=make_wav(seconds=10.0, amplitude=0.0)).status_code == 200


@pytest.mark.parametrize(
    ("kwargs", "status", "code"),
    [
        ({"icon": "teapot"}, 422, "bad_request"),
        ({"name": "   "}, 422, "bad_request"),
        ({"name": "x" * 41}, 422, "bad_request"),
        ({"room": make_wav(seconds=3.0)}, 400, "bad_audio"),
        ({"examples": [EX[0], EX[1], make_wav(channels=2)]}, 400, "bad_audio"),
        ({"examples": [EX[0], EX[1], make_wav(amplitude=0.0)]}, 400, "bad_audio"),
    ],
    ids=["bad_icon", "blank_name", "long_name", "short_room", "stereo_example", "silent_example"],
)
def test_teach_bad_input_skips_gemini(
    client: TestClient,
    fake_embed: FakeEmbed,
    kwargs: dict[str, object],
    status: int,
    code: str,
) -> None:
    res = post_teach(client, **kwargs)  # type: ignore[arg-type]
    assert res.status_code == status
    assert_error_shape(res.json(), code)
    assert fake_embed.calls == []
    assert store.taught_models() == []


def test_teach_missing_room(client: TestClient, fake_embed: FakeEmbed) -> None:
    files = {f"example_{i + 1}": (f"ex{i + 1}.wav", wav, "audio/wav") for i, wav in enumerate(EX)}
    res = client.post("/api/teach", data={"name": "Kettle"}, files=files)
    assert res.status_code == 422
    assert_error_shape(res.json(), "bad_request")


def test_room_windows_are_valid_clips() -> None:
    samples = audio.validate_clip(ROOM, seconds=10.0)
    windows = audio.room_windows(samples)
    assert len(windows) == 3
    for wav in windows:
        audio.validate_clip(wav)
