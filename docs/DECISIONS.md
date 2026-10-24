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
| Describe cap | 1 call per 10 s | At most 6 describe calls a minute (12 with retries), under 3.5 Flash-Lite's 15 RPM | `MAX_DESCRIBE_PER_SEC` |
| Gemini timeout / retries | 10 s / 1 retry on 429 or 5xx | Fail fast during a live demo | `api/` |
| Smoke-alarm rule | Beeps 0.3–0.8 s, gaps 0.3–0.8 s or 1.1–2.2 s, tone ≥ 40% of frame energy, ±5% steady | Tolerant T3 timing for phone mics and echo; tune with real recordings (#14) | `api/app/smoke_alarm.py` |
| Taught threshold mix | 0.5 (midpoint) | Threshold sits halfway between the room's best score and cos(example 1, example 2); tune with eval | `THRESHOLD_MIX` in `api/app/teach.py` |

## Log

### 2026-10-24 — Smoke alarm is built in, detected by a rule (P1)

- **Why not a tutorial:** asking every user to set off their own alarm (often on a high ceiling, painfully loud, sometimes wired to the whole building) to teach it was too much. The team wants smoke alarm built in.
- **Why a rule:** ESC-50 has no smoke alarms. Alarms are standardized: the T3 pattern (three 0.5 s beeps, 0.5 s apart, 1.5 s pause), usually a ~3 kHz piezo tone, some 520 Hz. `api/app/smoke_alarm.py` looks for a steady tone in those bands switching on and off in that rhythm. Any 3 s window of T3 holds at least two beeps.
- **Runs first, before the rate limiter and without Gemini:** a smoke alarm is never throttled, costs no quota, and still fires if Gemini is down. Live: ~35–140 ms vs ~800 ms for the embedding path. `confidence` is the mean tonality of the beeps (a rule score, not calibrated).
- **Known gap:** not yet measured on real alarms. Issue #14 asks P3 for real smoke-alarm clips and look-alikes (microwave beeps), which also lets us add smoke alarm to the classifier later.

### 2026-10-24 — Built-in classifier (P1)

- **Logistic regression on standardized embeddings, sigmoid-calibrated** (`CalibratedClassifierCV`, each calibrator fit on a held-out training fold). C chosen by leave-one-fold-out on folds 1–4 only; fold 5 is the untouched test set. Fold 5: 0.962 top-class accuracy, 0.865 with the p > 0.6 rule, and no "other" clip fired an alert. The 0.6 rule costs some recall but keeps false alarms down, which matters more for an alert app.
- **5 built-ins, not 6.** ESC-50 has no smoke alarm, so `builtin_smoke_alarm` stays in the Sounds list but never fires from the classifier until we have recordings.
- **eval/ runs in api/'s environment** (`uv run --project ../api`), so the saved `.joblib` is always loaded by the scikit-learn version that wrote it. The file records that version and the API warns on a mismatch; it refuses a model trained on a different embedding model or size.
- **A disabled built-in falls through** to the next step (loud → unknown, else none), the same as a disabled taught sound.

### 2026-10-24 — Describe unknown sounds with Gemini 3.5 Flash-Lite, not 3.8 Flash (P1)

- **Why:** on the free tier, Gemini 3.8 Flash allows 5 requests a minute and **20 a day**. During testing every call to it timed out (504 `DEADLINE_EXCEEDED`, even a text-only "say hello" with a 30 s timeout). Gemini 3.5 Flash-Lite allows **15 a minute and 500 a day**, accepts audio, and described a test beep in 1.3 s ("This is the sound of a digital watch alarm beeping, likely from a wristwatch."). 3.1 Flash-Lite has the same limits but took 4.7 s and wrote a longer line.
- **Describe cap:** at most 1 describe call every 10 s (`MAX_DESCRIBE_PER_SEC=0.1`). Over the cap, a loud unknown sound still returns `unknown`, with `description: null` and no API call.
- Embedding stays `gemini-embedding-2` (100 RPM, 1,000 RPD). The describe model is still a setting (`DESCRIBE_MODEL`), so switching back is one line in `api/.env`.

### 2026-10-24 — How a taught sound is matched (P1)

- **Prototype = normalized mean of examples 1 and 2.** Example 3 is held out for the self-check, so the check is honest.
- **Threshold = halfway between how similar the room is to the prototype and how similar examples 1 and 2 are to each other.** It adapts to each sound and room instead of one global number. Gemini audio embeddings sit close together (a beep scored 0.87 against a knock prototype in a live test), so a fixed cutoff would not work.
- **A match must beat the threshold and be closer to the prototype than to any room window.** `/teach`'s self-check and `/detect` use the same rule (`api/app/detectors.py`), so a passed self-check means example 3 would have been detected.
- **The room clip may be quiet.** A quiet room is valid; only the 3 examples are rejected as silent. The 10 s room clip becomes three 3 s windows (0, 3.5 and 7 s), so a teach costs 6 embed calls, run in parallel. No server cap on `/teach`; Gemini 429s still return `rate_limited`.

### 2026-10-24 — CI on every PR; no direct pushes to main (P1)

GitHub Actions runs three checks on every PR: `api tests`, `web build` and `no audio or secrets`. With self-merge, nobody else has to look at a PR before it lands, so CI is the safety net. `main` only accepts PRs with all three checks green.

### 2026-10-24 — Authors merge their own PRs; anyone updates docs for their own change (team)

- **Self-merge.** Every PR used to wait for one person to merge it. Now the author merges once it's ready: tests pass for `api/` and `eval/`, the build passes for `web/`. Root rule files need one other teammate from P1–P3, and `CONTRACT.md` still needs both P1 and P2. Always use a merge commit, so stacked PRs stay clean.
- **Shared docs.** Only P4 could edit `docs/`, so every change meant a hand-off and the docs fell behind. Now whoever makes a change updates the docs it affects in the same PR. P4 leads the demo script. Code folders keep their single owners.

### 2026-10-23 — Backend details (P1)

- **Detect cap is global, not per device.** One household, one API key; the cap protects our free-tier quota. Over the cap, `/detect` returns 429 with `retry_after_ms`.
- **IDs are 8 hex characters** (`evt_1a2b3c4d`), not 4 like the CONTRACT.md examples. 4 characters would repeat after a few hundred history events. Shape and prefix are unchanged.
- **Built-in sounds are seeded once.** Renaming or turning off a built-in survives a server restart.
- **History `since` includes events at that exact second.** No alert is lost; the frontend skips IDs it already has.

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
| python-multipart | api | FastAPI needs it to read uploaded audio files (`/detect`, `/teach`) | P1 |
| pytest | api (dev only) | Runs the backend tests required by api/AGENTS.md | P1 |
| httpx | api (dev only) | FastAPI's test client needs it | P1 |
| scikit-learn | api, eval | Built-in classifier (fixed stack); pulls in scipy, joblib and threadpoolctl | P1 |
