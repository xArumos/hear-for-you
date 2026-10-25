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
    smoke_alarm.py   # rule-based T3 smoke-alarm detector (no embedding)
    teach.py         # /teach: embeddings, prototype, self-check
    metrics.py       # serves metrics.json for GET /api/metrics
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
- Enforce `MAX_DETECT_PER_SEC` server-side; over the cap returns 429 with `retry_after_ms`. The smoke-alarm check runs before the cap (it costs no API call).
- `/detect` decision order:
  0. Smoke-alarm rule on the raw audio (T3 pattern, `smoke_alarm.py`). A match returns `builtin_smoke_alarm` with no Gemini call. If the alarm is disabled, remember that and keep going.
  1. Embed the clip.
  2. Score every taught sound (cosine to its prototype vs. to its room vectors). The best enabled match above its threshold wins. A match on a disabled one only marks the clip as suppressed.
  3. Otherwise run the built-in classifier; a calibrated probability above 0.6 wins if that sound is enabled. A disabled one marks the clip as suppressed.
  4. Otherwise, if nothing was suppressed and `level_db` is above the "loud" cutoff (default −20 dBFS), call the describe model (`gemini-3.5-flash-lite`, at most 1 call per 10 s) with the clip and `RELEVANCE_PROMPT` in `gemini.py`. It returns JSON `{relevant, description}`. Return `kind: "unknown"` only if it says relevant.
  5. Otherwise `kind: "none"`: quiet, suppressed, judged background, over the describe cap, or the describe call failed. Loudness alone never makes an alert.
- Taught, built-in and unknown results go through `ongoing.py`: the same sound detected again within `ONGOING_GAP_S` (10 s) of its last detection returns the open event's `event_id` and saves no new history row. Discrete sounds are never grouped (`UNGROUPED`: smoke alarm, door knock, glass breaking), so a second knock is a new alert.
- The describe prompt (`RELEVANCE_PROMPT`): one short plain sentence naming the likely source; `relevant` is false only for nothing but routine background (speech, typing, clicks, taps, footsteps, fans, hum), true if anything may need attention, even mixed with speech, and true when unsure. Keep the description under 80 characters; truncate if longer.
- Never store audio. Store embeddings and metadata only.
- Every response includes `latency_ms`. Log one line per request: route, status, latency, kind. No audio, no keys.
- `/detect` also logs one `detect ...` line per clip from `detectors.py`: level, smoke-rule score, best taught score vs. its threshold and room, top two built-in probabilities, the decision, why it was `none` (`disabled:<ids>`, `quiet`, `describe_cap`, `describe_failed`, `background`, or an error code), and whether the event was `new` or `grouped`. Sound IDs and numbers only: no audio, embeddings, descriptions or sound names.

## Tests (pytest)

- Contract shape tests for every endpoint, using a fake `gemini.py` (monkeypatch) so tests never call the network.
- Audio validation: wrong sample rate, stereo, wrong length, silence.
- Run `uv run pytest` before every PR.

## Don't

- Don't add endpoints or fields that aren't in `CONTRACT.md`.
- Don't import `google-genai` outside `gemini.py`.
- Don't load ESC-50 audio at request time; use the trained model and committed embeddings.
