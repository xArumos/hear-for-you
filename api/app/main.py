"""FastAPI app. Routes only; logic lives in the other app modules."""

import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Form, Query, Request, Response, UploadFile
from pydantic import BaseModel

from app import audio, gemini, ratelimit, store, teach
from app.config import settings
from app.errors import BadRequest, install_handlers

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


def _ms(start: float) -> int:
    return round((time.perf_counter() - start) * 1000)


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


@app.post("/api/teach")
def teach_sound(
    name: str = Form(...),
    example_1: UploadFile = File(...),
    example_2: UploadFile = File(...),
    example_3: UploadFile = File(...),
    room: UploadFile = File(...),
    icon: str = Form("generic"),
) -> dict[str, object]:
    start = time.perf_counter()
    examples = [f.file.read() for f in (example_1, example_2, example_3)]
    result = teach.teach(name, icon, examples, room.file.read())
    return {**result, "latency_ms": _ms(start)}


class SoundPatch(BaseModel):
    enabled: bool | None = None
    name: str | None = None


@app.get("/api/sounds")
def list_sounds() -> dict[str, object]:
    start = time.perf_counter()
    return {"sounds": store.list_sounds(), "latency_ms": _ms(start)}


@app.patch("/api/sounds/{sound_id}")
def patch_sound(sound_id: str, patch: SoundPatch) -> dict[str, object]:
    start = time.perf_counter()
    if patch.enabled is None and patch.name is None:
        raise BadRequest("Send enabled and/or name.")
    sound = store.update_sound(sound_id, enabled=patch.enabled, name=patch.name)
    return {**sound, "latency_ms": _ms(start)}


@app.delete("/api/sounds/{sound_id}")
def delete_sound(sound_id: str) -> dict[str, object]:
    start = time.perf_counter()
    store.delete_sound(sound_id)
    return {"deleted": True, "latency_ms": _ms(start)}


@app.get("/api/history")
def history(since: str | None = None, limit: int = Query(100, ge=1)) -> dict[str, object]:
    start = time.perf_counter()
    return {"events": store.list_events(since=since, limit=limit), "latency_ms": _ms(start)}
