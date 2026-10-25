"""Experimental (p1/gemma-experiment): load the local Gemma describe model and time it on a few WAV clips.

No Gemini calls and no ESC-50 download needed: pass any 16 kHz mono WAV files (the app's 3 s clips).
Prints where the model loaded (GPU or CPU, 4bit/8bit/bf16), the load time, then per clip the time and reply.

    uv run --project ../api python gemma_smoke.py clip1.wav clip2.wav
    DESCRIBE_MODEL=local:google/gemma-4-E2B-it GEMMA_QUANT=none uv run --project ../api python gemma_smoke.py a.wav
"""

import logging
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "api"))

from app import gemini, gemma_local  # noqa: E402
from app.config import settings  # noqa: E402

DEFAULT_MODEL = "local:google/gemma-4-E4B-it"


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit("usage: gemma_smoke.py clip.wav [clip.wav ...]")
    logging.basicConfig(level=logging.INFO, format="%(name)s %(message)s")
    model = settings.describe_model if settings.describe_model.startswith(gemini.LOCAL_PREFIX) else DEFAULT_MODEL
    model_id = model.removeprefix(gemini.LOCAL_PREFIX)
    start = time.monotonic()
    gemma_local.warm_up(model_id)
    print(f"load {time.monotonic() - start:.1f} s", flush=True)
    for path in sys.argv[1:]:
        start = time.monotonic()
        text = gemma_local.describe(model_id, gemini.RELEVANCE_PROMPT, Path(path).read_bytes())
        parsed = None if text is None else gemini._parse_described(text)
        print(f"{Path(path).name}: {time.monotonic() - start:.1f} s  {parsed or text!r}", flush=True)


if __name__ == "__main__":
    main()
