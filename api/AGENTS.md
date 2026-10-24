# api/AGENTS.md — backend rules (owner: P1)

Read the root `AGENTS.md` and `CONTRACT.md` first. This folder is the only place that talks to Gemini.

## Layout

```
api/
  app/
    main.py          # FastAPI app, routes only, no logic
    config.py        # reads api/.env (pydantic-settings or os.environ)
    gemini.py        # the ONLY module that imports google-genai
    audio.py         # WAV validation: 16 kHz, mono, 16-bit, 3.0 s (room 10.0 s)
    detectors.py     # built-in classifier, personal prototypes, unknown logic
    store.py         # SQLite: sounds, prototypes (as BLOB), history
    ratelimit.py     # MAX_DETECT_PER_SEC cap for /detect
    errors.py        # contract error shape + exception handlers
  models/
    builtin_clf.joblib   # trained by eval/, loaded at startup
  metrics.json       # written by eval/, served by GET /api/metrics
  tests/
  pyproject.toml
  .env.example
```

## Rules

- `main.py` holds routes only. Logic goes in the modules above.
- All Gemini calls go through `gemini.py`, with: 10 s timeout, one retry on 429/5xx, then raise an error that maps to the contract's `rate_limited` or `upstream_error`.
- Embed with `gemini-embedding-2`, `output_dimensionality = EMBED_DIM` (768). Normalize vectors to unit length before storing or comparing.
- Validate audio before any Gemini call. A bad clip returns 400 `bad_audio` and costs no API call.
- Enforce `MAX_DETECT_PER_SEC` server-side; over the cap returns 429 with `retry_after_ms`.
- `/detect` decision order:
  1. Embed the clip.
  2. Score every enabled taught sound (cosine to its prototype vs. to its room vectors). A match above its threshold wins.
  3. Otherwise run the built-in classifier; a calibrated probability above 0.6 wins.
  4. Otherwise, if `level_db` is above the "loud" cutoff (default −20 dBFS), call Gemini 3.8 Flash with the clip and the prompt in `gemini.py`, and return `kind: "unknown"`.
  5. Otherwise `kind: "none"`.
- The describe prompt: *"Describe this sound in one short, plain sentence for someone who cannot hear it. Name the likely source. No preamble."* Keep the output under 80 characters; truncate if longer.
- Never store audio. Store embeddings and metadata only.
- Every response includes `latency_ms`. Log one line per request: route, status, latency, kind. No audio, no keys.

## Tests (pytest)

- Contract shape tests for every endpoint, using a fake `gemini.py` (monkeypatch) so tests never call the network.
- Audio validation: wrong sample rate, stereo, wrong length, silence.
- Run `uv run pytest` before every PR.

## Don't

- Don't add endpoints or fields that aren't in `CONTRACT.md`.
- Don't import `google-genai` outside `gemini.py`.
- Don't load ESC-50 audio at request time; use the trained model and committed embeddings.
