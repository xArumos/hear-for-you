"""Experimental: run an open Gemma model locally to describe unknown sounds.

Used when DESCRIBE_MODEL is "local:<hugging face id>", e.g. "local:google/gemma-4-E4B-it". The Gemini API's
hosted Gemma models reject audio, so the audio-capable small Gemma 4 models run here: on an NVIDIA GPU if
torch sees one, else on CPU (about 35 s per clip for E4B on a laptop, too slow for live use).
Needs the optional deps: `uv sync --group gemma-gpu` or `--group gemma-cpu`. torch/transformers are imported
only when this is used.
"""

import io
import logging
import threading
import time
from typing import Any

import numpy as np
import soundfile as sf

from app.config import settings

log = logging.getLogger("hear-for-you.gemma")

MAX_NEW_TOKENS = 60
# Kept at full precision when quantizing: the audio encoder decides what the model hears.
SKIP_QUANT = ["audio_tower", "embed_audio", "vision_tower", "embed_vision", "lm_head"]
JSON_INSTRUCTION = ' Reply with only a JSON object: {"relevant": true or false, "description": "..."}.'

_lock = threading.Lock()
_loaded: tuple[str, Any, Any] | None = None  # (model id, processor, model)


def _quant(cuda: bool) -> str:
    """GEMMA_QUANT: auto (4bit on GPU, none on CPU), none, 8bit or 4bit."""
    if settings.gemma_quant == "auto":
        return "4bit" if cuda else "none"
    return settings.gemma_quant


def _load_kwargs() -> dict[str, Any]:
    import torch

    cuda = torch.cuda.is_available()
    kwargs: dict[str, Any] = {"dtype": torch.bfloat16}
    if not cuda:
        kwargs["device_map"] = "cpu"
        return kwargs
    # Cap GPU memory; anything that doesn't fit spills to system RAM (slower) instead of running out.
    kwargs["device_map"] = "auto"
    kwargs["max_memory"] = {0: settings.gemma_gpu_memory, "cpu": "48GiB"}
    quant = _quant(cuda)
    if quant in ("4bit", "8bit"):
        from transformers import BitsAndBytesConfig

        kwargs["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=quant == "4bit",
            load_in_8bit=quant == "8bit",
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16,
            llm_int8_skip_modules=SKIP_QUANT,
            llm_int8_enable_fp32_cpu_offload=True,
        )
    return kwargs


def _load(model_id: str) -> tuple[Any, Any]:
    global _loaded
    if _loaded is None or _loaded[0] != model_id:
        from transformers import AutoModelForMultimodalLM, AutoProcessor

        start = time.monotonic()
        kwargs = _load_kwargs()
        processor = AutoProcessor.from_pretrained(model_id)
        model = AutoModelForMultimodalLM.from_pretrained(model_id, **kwargs)
        model.eval()
        _loaded = (model_id, processor, model)
        quant = kwargs.get("quantization_config")
        log.info(
            "loaded %s on %s (%s) in %d ms",
            model_id,
            model.device,
            "4bit" if quant and quant.load_in_4bit else "8bit" if quant else "bf16",
            int((time.monotonic() - start) * 1000),
        )
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
        ).to(model.device)
        prompt_len = inputs["input_ids"].shape[-1]
        with torch.inference_mode():
            output = model.generate(**inputs, max_new_tokens=MAX_NEW_TOKENS, do_sample=False)
        return str(processor.decode(output[0][prompt_len:], skip_special_tokens=True))
    except Exception as exc:
        log.warning("local describe failed: %s", type(exc).__name__)
        return None
    finally:
        _lock.release()
