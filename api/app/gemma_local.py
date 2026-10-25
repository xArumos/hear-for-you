"""Experimental: run an open Gemma model locally to describe unknown sounds.

Used when DESCRIBE_MODEL is "local:<hugging face id>", e.g. "local:google/gemma-4-E4B-it". The Gemini API's
hosted Gemma models reject audio, so the audio-capable small Gemma 4 models run here on CPU.
Needs the optional deps: `uv sync --group gemma`. torch/transformers are imported only when this is used.
"""

import io
import logging
import threading
import time
from typing import Any

import numpy as np
import soundfile as sf

log = logging.getLogger("hear-for-you.gemma")

MAX_NEW_TOKENS = 60
JSON_INSTRUCTION = ' Reply with only a JSON object: {"relevant": true or false, "description": "..."}.'

_lock = threading.Lock()
_loaded: tuple[str, Any, Any] | None = None  # (model id, processor, model)


def _load(model_id: str) -> tuple[Any, Any]:
    global _loaded
    if _loaded is None or _loaded[0] != model_id:
        import torch
        from transformers import AutoModelForMultimodalLM, AutoProcessor

        start = time.monotonic()
        processor = AutoProcessor.from_pretrained(model_id)
        model = AutoModelForMultimodalLM.from_pretrained(model_id, dtype=torch.bfloat16, device_map="cpu")
        model.eval()
        _loaded = (model_id, processor, model)
        log.info("loaded %s in %d ms", model_id, int((time.monotonic() - start) * 1000))
    return _loaded[1], _loaded[2]


def warm_up(model_id: str) -> None:
    """Load the model now so the first unknown sound isn't slowed by a long load."""
    with _lock:
        try:
            _load(model_id)
        except Exception as exc:
            log.warning("local model load failed: %s", type(exc).__name__)


def describe(model_id: str, prompt: str, wav: bytes) -> str | None:
    """Raw text reply from the local model, or None if it is busy or fails."""
    if not _lock.acquire(blocking=False):
        log.warning("describe skipped: local model busy")
        return None
    try:
        import torch

        processor, model = _load(model_id)
        audio, _ = sf.read(io.BytesIO(wav), dtype="float32")
        if audio.ndim > 1:
            audio = np.mean(audio, axis=1)
        conversation = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt + JSON_INSTRUCTION},
                    {"type": "audio", "audio": audio},
                ],
            }
        ]
        inputs = processor.apply_chat_template(
            conversation, tokenize=True, return_dict=True, return_tensors="pt", add_generation_prompt=True
        )
        prompt_len = inputs["input_ids"].shape[-1]
        with torch.inference_mode():
            output = model.generate(**inputs, max_new_tokens=MAX_NEW_TOKENS, do_sample=False)
        return str(processor.decode(output[0][prompt_len:], skip_special_tokens=True))
    except Exception as exc:
        log.warning("local describe failed: %s", type(exc).__name__)
        return None
    finally:
        _lock.release()
