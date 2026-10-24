# DECISIONS.md — why things are the way they are

Read before changing the stack, a model, or a constant. Add a new entry (newest first) when you change one. Format: date, decision, why, who.

## Constants

| Constant | Value | Why | Where |
| --- | --- | --- | --- |
| Clip length | 3.0 s | Long enough for a knock or beep, short enough for low latency | `api/`, `web/` |
| Room clip | 10.0 s | Enough background to model "not this" | `api/`, `web/` |
| Sample format | 16 kHz, mono, 16-bit PCM WAV | Embedding 2 accepts wav or mp3 only; small uploads | everywhere |
| Embedding size | 768 | Faster training and search than the 3,072 default | `EMBED_DIM` |
| Gate threshold | room baseline + 12 dB | Starting value; tune Saturday | `web/` |
| Detect cap | 1 call per second | Stay under free-tier limits | `MAX_DETECT_PER_SEC` |
| Gemini timeout / retries | 10 s / 1 retry on 429 or 5xx | Fail fast during a live demo | `api/` |

## Log

### 2026-10-23 — Stack fixed for the event (team)

- **Gemini Embedding 2 + our own detectors** instead of a pre-trained sound classifier. Embedding 2 (GA Apr 22, 2026) is the recent tech the challenge requires, puts audio and text in one space (zero-shot baseline), and lets us show our own ML.
- **Gemini 3.8 Flash** for describing unknown sounds. GA Sep 2, 2026; free tier; accepts audio.
- **Web app, not native.** Runs on Linux dev machines and any phone; no app-store builds. Accepted cost: Wake Lock required, no vibration on iPhone.
- **FastAPI + SQLite.** Simplest Python server that the ML code can live in; one file database.
- **React + Vite + Tailwind.** Fast to build with AI tools; no UI kit to fight.
- **uv for Python, npm for Node.** One lockfile each; same versions on every machine.
- **No raw audio in git.** ESC-50 is CC BY-NC and our recordings are personal; we commit embeddings and manifests.

### 2026-10-23 — Pivoted from bird detection to HearAlert (team)

Team preferred a non-bird topic. Same "record, detect, alert" pattern, stronger social impact, and Gemini becomes core.

## Dependencies

Add a row for every dependency beyond the fixed stack in `AGENTS.md`.

| Package | Folder | Why | Added by |
| --- | --- | --- | --- |
| _none yet_ | | | |
