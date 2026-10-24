"""gemini.py retry and mapping logic, against a fake client. No network."""

from collections.abc import Callable
from types import SimpleNamespace

import httpx
import numpy as np
import pytest
from google.genai import errors, types

from app import gemini
from app.errors import RateLimited, UpstreamError


def api_error(code: int) -> errors.APIError:
    return errors.APIError(code, {"error": {"code": code, "message": "fake", "status": "FAKE"}})


def ok_response(values: list[float]) -> types.EmbedContentResponse:
    return types.EmbedContentResponse(embeddings=[types.ContentEmbedding(values=values)])


class FakeModels:
    def __init__(self, outcomes: list[Callable[[], object]]) -> None:
        self.outcomes = outcomes
        self.calls: list[dict[str, object]] = []

    def _next(self, kwargs: dict[str, object]) -> object:
        self.calls.append(kwargs)
        return self.outcomes[len(self.calls) - 1]()

    def embed_content(self, **kwargs: object) -> object:
        return self._next(kwargs)

    def generate_content(self, **kwargs: object) -> object:
        return self._next(kwargs)


def install_fake(
    monkeypatch: pytest.MonkeyPatch, outcomes: list[Callable[[], object]]
) -> FakeModels:
    models = FakeModels(outcomes)
    monkeypatch.setattr(gemini, "_get_client", lambda: SimpleNamespace(models=models))
    monkeypatch.setattr(gemini, "RETRY_DELAY_S", 0.0)
    return models


def raises(exc: Exception) -> Callable[[], object]:
    def fn() -> object:
        raise exc

    return fn


def test_embed_normalizes_and_requests_768(monkeypatch: pytest.MonkeyPatch) -> None:
    models = install_fake(monkeypatch, [lambda: ok_response([3.0, 4.0])])
    vec = gemini.embed_audio(b"wav")
    np.testing.assert_allclose(vec, [0.6, 0.8], rtol=1e-6)
    call = models.calls[0]
    assert call["model"] == "gemini-embedding-2"
    config = call["config"]
    assert isinstance(config, types.EmbedContentConfig)
    assert config.output_dimensionality == 768


@pytest.mark.parametrize(
    "first_error",
    [api_error(429), api_error(503), httpx.ReadTimeout("slow")],
    ids=["429", "503", "timeout"],
)
def test_retries_once_then_succeeds(
    monkeypatch: pytest.MonkeyPatch, first_error: Exception
) -> None:
    models = install_fake(monkeypatch, [raises(first_error), lambda: ok_response([1.0, 0.0])])
    gemini.embed_audio(b"wav")
    assert len(models.calls) == 2


def test_two_429s_raise_rate_limited(monkeypatch: pytest.MonkeyPatch) -> None:
    models = install_fake(monkeypatch, [raises(api_error(429)), raises(api_error(429))])
    with pytest.raises(RateLimited) as exc:
        gemini.embed_audio(b"wav")
    assert exc.value.retry_after_ms > 0
    assert len(models.calls) == 2


def test_two_5xx_raise_upstream(monkeypatch: pytest.MonkeyPatch) -> None:
    models = install_fake(monkeypatch, [raises(api_error(500)), raises(api_error(503))])
    with pytest.raises(UpstreamError):
        gemini.embed_audio(b"wav")
    assert len(models.calls) == 2


def test_400_is_not_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    models = install_fake(monkeypatch, [raises(api_error(400))])
    with pytest.raises(UpstreamError):
        gemini.embed_audio(b"wav")
    assert len(models.calls) == 1


def test_empty_embedding_is_upstream_error(monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake(monkeypatch, [lambda: types.EmbedContentResponse(embeddings=[])])
    with pytest.raises(UpstreamError):
        gemini.embed_audio(b"wav")


def text_response(text: str) -> types.GenerateContentResponse:
    return types.GenerateContentResponse(
        candidates=[types.Candidate(content=types.Content(role="model", parts=[types.Part(text=text)]))]
    )


def test_describe_sends_prompt_and_audio(monkeypatch: pytest.MonkeyPatch) -> None:
    models = install_fake(monkeypatch, [lambda: text_response(" A dog barking outside.\n")])
    assert gemini.describe_audio(b"wav") == "A dog barking outside."
    call = models.calls[0]
    assert call["model"] == "gemini-3.8-flash"
    prompt, part = call["contents"]  # type: ignore[misc]
    assert prompt == gemini.DESCRIBE_PROMPT
    assert part.inline_data.mime_type == "audio/wav" and part.inline_data.data == b"wav"


def test_describe_truncates_long_text(monkeypatch: pytest.MonkeyPatch) -> None:
    long = "A very loud metal pot falling onto a hard kitchen floor and bouncing several times"
    install_fake(monkeypatch, [lambda: text_response(long)])
    text = gemini.describe_audio(b"wav")
    assert text is not None and len(text) < 80 and text.endswith("…")
    assert text.startswith("A very loud metal pot")


@pytest.mark.parametrize(
    "outcomes",
    [[raises(api_error(429)), raises(api_error(429))], [raises(api_error(400))], [lambda: text_response("  ")]],
    ids=["rate_limited", "bad_request", "empty"],
)
def test_describe_failure_returns_none(
    monkeypatch: pytest.MonkeyPatch, outcomes: list[Callable[[], object]]
) -> None:
    install_fake(monkeypatch, outcomes)
    assert gemini.describe_audio(b"wav") is None
