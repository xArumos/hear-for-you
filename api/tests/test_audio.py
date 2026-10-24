import numpy as np
import pytest

from app.audio import validate_clip
from app.errors import BadAudio
from tests.conftest import make_wav


def test_valid_clip_returns_samples() -> None:
    samples = validate_clip(make_wav())
    assert samples.shape == (48_000,)
    assert np.max(np.abs(samples)) > 0.4


def test_room_clip_length() -> None:
    validate_clip(make_wav(seconds=10.0), seconds=10.0)


@pytest.mark.parametrize(
    ("wav", "fragment"),
    [
        (make_wav(rate=44_100), "44100 Hz"),
        (make_wav(channels=2), "2 channels"),
        (make_wav(seconds=2.5), "2.50 s"),
        (make_wav(seconds=3.1), "3.10 s"),
        (make_wav(subtype="PCM_U8"), "PCM_U8"),
        (make_wav(amplitude=0.0), "silent"),
        (b"definitely not a wav file", "Not a readable WAV"),
    ],
    ids=["sample_rate", "stereo", "too_short", "too_long", "8_bit", "silence", "not_wav"],
)
def test_bad_clips_raise_bad_audio(wav: bytes, fragment: str) -> None:
    with pytest.raises(BadAudio) as exc:
        validate_clip(wav)
    assert fragment in exc.value.message
