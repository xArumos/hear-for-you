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
| Ongoing-event gap | 10 s | Notification grouping, not an ML threshold: the same sound detected again within 10 s of its last detection is one history event (smoke alarm excluded). Matches P2's frontend grouping | `ONGOING_GAP_S` in `api/app/ongoing.py` |
| Taught threshold mix | 0.5 (midpoint) | Threshold sits halfway between the room's best score and cos(example 1, example 2); tune with eval | `THRESHOLD_MIX` in `api/app/teach.py` |

## Log

### 2026-10-24 — Bundle the existing frontend for foreground iOS use (P2, user approved)

Capacitor 8.5.3 core/CLI/iOS were already in web/package.json and its lockfile.
Reuse those packages, React components, API client, Web Audio/WAV encoder and guest
storage; no extra native plugin or UI framework. Add the generated iOS/SPM project
under web/ios and keep website builds independent. The native display name
HearAlert is explicitly requested; dev.hearforyou.app is provisional. Use an
ignored build-time HTTPS backend origin; Capacitor's built-in HTTP fetch bridge
supports multipart uploads without editing P1 CORS. No key goes into the bundle.
Foreground-only capture stops on background/interruption; no background modes,
silent audio, auto-resume or native notification claims. Native-only safe-area
CSS preserves the website layout. Full Xcode and physical-device verification
are outstanding; see IOS.md. This supersedes the web-only deployment choice for
the requested iOS target, while retaining the existing website.

### 2026-10-24 — Backend decides relevance before history (P1, issue #22)

- **Unknown alerts need the describe model's relevance flag.** The describe call now returns JSON
  `{relevant, description}` (same model, structured output). A loud clip that is only background, that the model
  can't judge (call failed, over the describe cap), or that matched a disabled sound is `none` and is not saved.
  Before, loudness alone made an `unknown` event. The flag is model judgement, not a calibrated confidence. The
  prompt says "relevant if unsure" so a missed alarm is less likely than a stray alert.
- **Disabled sounds are suppressed, not relabelled.** A disabled smoke alarm, built-in or taught match makes the
  clip `none`, but an enabled sound in the same clip still wins. Re-enabling works on the next clip.
- **Ongoing sounds are one history event.** See `ONGOING_GAP_S`. The repeat returns the open `event_id`, which
  the frontend already ignores, so alerts and history agree. The smoke alarm is never grouped so it keeps alerting.
- Measured on held-out ESC-50 clips by `eval/eval_relevance.py`; numbers in `docs/MODEL_CARD.md`.

### 2026-10-24 — Conservative frontend alert relevance and grouping (P2)

The existing capture baseline + 12 dB, microphone constraints, model and backend
thresholds stay unchanged. A shared frontend admission decision feeds both the
visual alert and local History. Empty unknown descriptions, generic loud-noise
fallbacks, and a narrow set of complete background-only descriptions are not
admitted. Mixed-event descriptions are not rejected by individual speech/typing
keywords. This is a text presentation filter, not validated audio classification;
paraphrases can escape it, and descriptions can omit a real simultaneous event.
Meaningful unknown descriptions remain eligible without invented confidence.

Recognized results must refer to an enabled sound and have finite scores in
[0, 1]. The frontend mirrors the backend's existing > 0.6 built-in rule and >= 0.5
taught score mapping; the smoke-alarm rule is exempt from the classifier cutoff.
Taught confidence is a threshold-relative mapping, not a calibrated probability.
No higher global or unvalidated class-specific confidence threshold is introduced.

Barks, sirens and crying alert immediately on the first admitted result. Continued
observations less than 10 seconds apart group into the same local event. The
interval is a notification policy, not an empirically validated classifier
constant. A gap in observations rearms the category; missed observations can
split an ongoing event, and distinct events less than 10 seconds apart can group.
Glass breaks, smoke alarms, knocks and taught sounds require no repetition and
have no category cooldown. Duplicate admitted API event IDs are ignored for the
lifetime of the app. Backend History is written before this frontend policy and
requires P1 changes to adopt the same rules. No contract change is proposed here.

### 2026-10-24 — Renamed the app to Hear For You (team)

The app is now **Hear For You**, with the motto "Here when it matters. Hearing what matters.", from P4's Figma design. All
docs and UI text use the new name. Lowercase `hearalert` stays as a technical identifier only (GitHub repo and folder,
`hearalert.db`, package and logger names): renaming those would break clones, CI and everyone's local database for no
user-visible gain. Approved by P1 and P3.

### 2026-10-24 — Technical identifiers renamed to hear-for-you (P1, P3)

Superseding the entry above: the GitHub repo is now `xArumos/hear-for-you`, and the technical identifiers follow it
for consistency: `hear-for-you.db`, `hear-for-you-api`, `hear-for-you-data`, and `hear-for-you.*` loggers. GitHub
redirects the old repo URL. An existing local `hearalert.db` is no longer used by default: rename it to
`hear-for-you.db` to keep taught sounds. Approved by P1 and P3.

### 2026-10-24 — /api/metrics shows only measured numbers (P1)

- `eval/write_metrics.py` fills a field only when the script that measures it has written its results CSV; everything else is `null`, so the Model Card page never shows a placeholder as if it were real. Today only the trained built-in accuracy is measured.
- `builtin_accuracy.trained` is the accuracy **with the p > 0.6 rule `/detect` uses** (0.865), not plain top-class accuracy (0.962): it is the number users actually get. The Model Card lists both.
- `api/metrics.json` is committed and re-read on every request; if it is missing, `/api/metrics` returns 404 `not_found`.

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

### 2026-10-23 — Pivoted from bird detection to Hear For You (team)

Team preferred a non-bird topic. Same "record, detect, alert" pattern, stronger social impact, and Gemini becomes core.

## Dependencies

Add a row for every dependency beyond the fixed stack in `AGENTS.md`.

| Package | Folder | Why | Added by |
| --- | --- | --- | --- |
| @capacitor/core 8.5.3 | web | Existing native bridge and HTTP support; reused for requested iOS target | P2 |
| @capacitor/ios 8.5.3 | web | Existing WKWebView runtime / Swift package; reused | P2 |
| @capacitor/cli 8.5.3 | web | Existing native project generation/sync tooling; reused | P2 |
| python-multipart | api | FastAPI needs it to read uploaded audio files (`/detect`, `/teach`) | P1 |
| pytest | api (dev only) | Runs the backend tests required by api/AGENTS.md | P1 |
| httpx | api (dev only) | FastAPI's test client needs it | P1 |
| scikit-learn | api, eval | Built-in classifier (fixed stack); pulls in scipy, joblib and threadpoolctl | P1 |
