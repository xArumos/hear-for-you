# Gemma experiment — run the describe step on an open Gemma model

Branch `p1/gemma-experiment` only. **Not for `main`** until the team agrees (see "Before merging").

Hear For You calls a generative model in one place: describing a loud sound nobody taught it and judging whether
it matters (`gemini.describe_relevance`). This branch lets that step run on **Gemma 4**, Google's open-weights
model (Apache 2.0), on your own machine. Everything else is unchanged; embeddings still use
`gemini-embedding-2`, because no Gemma model turns audio into vectors.

Why local: the Gemini API hosts `gemma-4-31b-it` and `gemma-4-26b-a4b-it`, but both reject audio
(`400 Audio input modality is not enabled for this model`). The audio-capable Gemma 4 models are the small
**E4B** and **E2B**, which you download from Hugging Face and run with `transformers`.

## What you need

- An NVIDIA GPU with a driver that supports CUDA 12.6 (driver 560 or newer). Tested plan: RTX 4070 Ti, 12 GB.
  CPU works too but takes about 35 s per sound (E4B, laptop), too slow for live use.
- About 16 GB of disk for the E4B weights (cached in `~/.cache/huggingface`, outside the repo), 10 GB for E2B.
- The usual setup from `docs/SETUP.md` (uv, Python 3.12, Node 22) and a `GEMINI_API_KEY` in `api/.env`
  (still needed for embeddings).

## Steps (Linux or Windows; commands are the same in PowerShell)

```bash
git fetch origin
git checkout p1/gemma-experiment
cd api
uv sync --group gemma-gpu        # CUDA torch + transformers + bitsandbytes (a few GB)
uv run python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
```

That should print `True NVIDIA GeForce RTX 4070 Ti`. If it prints `False`, update the NVIDIA driver.

Add to `api/.env`:

```
DESCRIBE_MODEL=local:google/gemma-4-E4B-it
GEMMA_QUANT=auto
GEMMA_GPU_MEMORY=10GiB
```

**Smoke test** (no Gemini calls; first run downloads the model). Pass any 16 kHz mono WAV clips, for example a
few from `data/raw/converted/` copied over from another machine (never commit them):

```bash
cd eval
uv run --project ../api python gemma_smoke.py dog.wav siren.wav
```

It prints where the model loaded (`cuda:0 (4bit)`), the load time, and per clip the time and the reply.

**Run the app** as usual, but without `--reload` (a reload would load the model again):

```bash
cd api
uv run uvicorn app.main:app --port 8000
```

The server starts at once and loads Gemma in the background; the log says
`hear-for-you.gemma loaded google/gemma-4-E4B-it on cuda:0 (4bit) in ... ms`. Until then (and while Gemma is busy
with another clip) loud unknown sounds return `none`. `curl localhost:8000/api/health` shows
`"describe": "local:google/gemma-4-E4B-it"`. Then start `web/` as in `docs/SETUP.md`.

To switch back to Gemini, delete the `DESCRIBE_MODEL` line (or set it to `gemini-3.5-flash-lite`).

## Settings

| Setting | Default | Meaning |
| --- | --- | --- |
| `DESCRIBE_MODEL` | `gemini-3.5-flash-lite` | `local:<hugging face id>` runs that model locally |
| `GEMMA_QUANT` | `auto` | `auto` = 4-bit on GPU, full precision on CPU. Or `none`, `8bit`, `4bit` |
| `GEMMA_GPU_MEMORY` | `10GiB` | Most GPU memory to use; the rest of the model goes to system RAM (slower) |

Memory: E4B has 8B parameters, 2.8B of them in a per-layer embedding table that 4/8-bit quantization does not
shrink. Rough GPU sizes: full precision about 16 GB (does not fit 12 GB), 8-bit about 12 GB (borderline),
4-bit about 10 GB. The audio encoder is never quantized. If 4-bit is too slow or spills to RAM, try
`DESCRIBE_MODEL=local:google/gemma-4-E2B-it` with `GEMMA_QUANT=none` (about 10 GB).

## How well it works (so far)

| Model | Where | Load | Per 3 s clip | Notes |
| --- | --- | --- | --- | --- |
| Gemini 3.5 Flash-Lite | API | – | ~1.3 s | Current default |
| Gemma 4 E4B, bf16 | Laptop CPU (22 cores) | 3 s cached | ~34 s | Valid JSON. Dog: "A dog is barking." but relevant=false. Crying baby: "low hum from the air conditioning". Car horn: judged background |
| Gemma 4 E2B, bf16 | Laptop CPU | – | ~19 s | "No discernible sounds" on dog and crying baby |
| Gemma 4 E4B, 4-bit | RTX 4070 Ti | ? | ? | To measure |

Only a handful of clips so far: an early look, not an evaluation. For real numbers run the held-out relevance eval
with Gemma (writes `eval/results/relevance_test_gemma_*.csv`; needs the ESC-50 archive and ffmpeg, see the
script's docstring) and compare with `relevance_test_summary.csv`:

```bash
cd eval
uv run --project ../api python eval_relevance.py test
```

Ideas if it hears poorly: a shorter prompt (`RELEVANCE_PROMPT` is tuned for Gemini), E4B at `8bit` or `none`.

## Before merging

Needs team agreement first: `AGENTS.md` §4 allows only the two Gemini models; `CONTRACT.md` shows the
default describe model in `/api/health`; new dependencies go in `docs/DECISIONS.md` (done on this branch).
