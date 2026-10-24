"""FastAPI app. Routes only; logic lives in the other app modules."""

import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Form, Request, Response, UploadFile

from app import audio, gemini, ratelimit, store
from app.config import settings
from app.errors import install_handlers

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("hearalert.api")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    store.init_db()
    yield


app = FastAPI(title="HearAlert API", lifespan=lifespan)
install_handlers(app)


@app.middleware("http")
async def log_request(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    start = time.perf_counter()
    response = await call_next(request)
    ms = round((time.perf_counter() - start) * 1000)
    kind = getattr(request.state, "kind", "-")
    log.info(
        "%s %s status=%d latency_ms=%d kind=%s",
        request.method, request.url.path, response.status_code, ms, kind,
    )
    return response


@app.get("/api/health")
def health() -> dict[str, object]:
    return {
        "ok": True,
        "models": {"embed": settings.embed_model, "describe": settings.describe_model},
    }


@app.post("/api/detect")
def detect(
    request: Request,
    clip: UploadFile = File(...),
    level_db: float = Form(...),
) -> dict[str, object]:
    start = time.perf_counter()
    ratelimit.detect_limiter.check()
    data = clip.file.read()
    audio.validate_clip(data)
    gemini.embed_audio(data)
    # Detectors (taught, built-in, unknown) are not wired yet; every clip is "none" for now.
    request.state.kind = "none"
    return {
        "event_id": store.new_id("evt"),
        "kind": "none",
        "label": None,
        "sound_id": None,
        "confidence": None,
        "description": None,
        "latency_ms": round((time.perf_counter() - start) * 1000),
    }
