"""The only module that talks to Gemini. 10 s timeout, one retry on 429/5xx/timeout."""

import logging
import time
from collections.abc import Callable
from typing import TypeVar

import httpx
import numpy as np
from google import genai
from google.genai import errors, types

from app.config import settings
from app.errors import ApiError, RateLimited, UpstreamError

log = logging.getLogger("hear-for-you.gemini")

TIMEOUT_MS = 10_000
RETRY_DELAY_S = 0.5
DEFAULT_RETRY_AFTER_MS = 1_000

DESCRIBE_PROMPT = (
    "Describe this sound in one short, plain sentence for someone who cannot hear it. "
    "Name the likely source. No preamble."
)
MAX_DESCRIPTION_CHARS = 80

T = TypeVar("T")

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        if not settings.gemini_api_key:
            raise UpstreamError("GEMINI_API_KEY is not set in api/.env.")
        _client = genai.Client(
            api_key=settings.gemini_api_key,
            http_options=types.HttpOptions(timeout=TIMEOUT_MS),
        )
    return _client


def _is_retryable(exc: Exception) -> bool:
    if isinstance(exc, errors.APIError):
        return exc.code == 429 or exc.code >= 500
    return isinstance(exc, (httpx.TimeoutException, httpx.TransportError))


def _call_with_retry(fn: Callable[[], T]) -> T:
    """Run fn; retry once on a retryable failure; map the final failure to a contract error."""
    for attempt in (1, 2):
        try:
            return fn()
        except Exception as exc:
            if not _is_retryable(exc):
                log.warning("gemini call failed (not retryable): %s", type(exc).__name__)
                raise UpstreamError("Gemini request failed.") from exc
            if attempt == 1:
                log.info("gemini call failed, retrying once: %s", type(exc).__name__)
                time.sleep(RETRY_DELAY_S)
                continue
            if isinstance(exc, errors.APIError) and exc.code == 429:
                raise RateLimited(
                    "Gemini rate limit reached. Try again shortly.",
                    retry_after_ms=DEFAULT_RETRY_AFTER_MS,
                ) from exc
            raise UpstreamError("Gemini failed after one retry.") from exc
    raise AssertionError("unreachable")


def embed_audio(wav: bytes) -> np.ndarray:
    """Embed a WAV clip with gemini-embedding-2; return a unit-length float32 vector of EMBED_DIM."""
    client = _get_client()

    def call() -> types.EmbedContentResponse:
        return client.models.embed_content(
            model=settings.embed_model,
            contents=types.Part.from_bytes(data=wav, mime_type="audio/wav"),
            config=types.EmbedContentConfig(output_dimensionality=settings.embed_dim),
        )

    response = _call_with_retry(call)
    if not response.embeddings or not response.embeddings[0].values:
        raise UpstreamError("Gemini returned no embedding.")
    vector = np.asarray(response.embeddings[0].values, dtype=np.float32)
    norm = float(np.linalg.norm(vector))
    if norm == 0.0:
        raise UpstreamError("Gemini returned a zero embedding.")
    return vector / norm


def _shorten(text: str) -> str:
    """One line, under MAX_DESCRIPTION_CHARS; cut at a word boundary and add an ellipsis if needed."""
    line = " ".join(text.split())
    if len(line) < MAX_DESCRIPTION_CHARS:
        return line
    cut = line[: MAX_DESCRIPTION_CHARS - 2].rsplit(" ", 1)[0].rstrip(" ,;:.")
    return cut + "…"


def describe_audio(wav: bytes) -> str | None:
    """One plain sentence about an unknown sound from the describe model, or None if the call fails."""
    try:
        client = _get_client()

        def call() -> types.GenerateContentResponse:
            return client.models.generate_content(
                model=settings.describe_model,
                contents=[DESCRIBE_PROMPT, types.Part.from_bytes(data=wav, mime_type="audio/wav")],
            )

        response = _call_with_retry(call)
    except ApiError as exc:
        log.warning("describe failed: %s", exc.code)
        return None
    text = (response.text or "").strip()
    return _shorten(text) if text else None
