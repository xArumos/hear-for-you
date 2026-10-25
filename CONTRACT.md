# CONTRACT.md — API contract between `web/` and `api/`

This file is the agreement between frontend and backend. **Changes need P1 and P2 to agree in a PR.**
Fixtures that match every response below live in `web/src/fixtures/`, so the frontend never waits on the backend.

## Basics

- Base path: `/api`. In development, Vite proxies `/api` to `http://localhost:8000`.
- Audio uploads: `multipart/form-data`, field type `audio/wav`, **16 kHz, mono, 16-bit PCM, 3.0 s** (room clip: 10.0 s).
- Times: ISO 8601 UTC strings. IDs: short strings (`snd_…`, `evt_…`).
- Every response includes `latency_ms` (server time spent, integer) except `GET /api/health`.

## Error shape (every non-2xx response)

```json
{ "error": { "code": "bad_audio", "message": "Clip must be 16 kHz mono WAV, 3.0 s." } }
```

| HTTP | `code` | When |
| --- | --- | --- |
| 400 | `bad_audio` | Wrong format, length, or silent clip |
| 404 | `not_found` | Unknown `sound_id` or `event_id` |
| 422 | `bad_request` | Missing or invalid field |
| 429 | `rate_limited` | Our per-second cap or Gemini's free-tier limit was hit. Includes `"retry_after_ms"` |
| 502 | `upstream_error` | Gemini failed after one retry |

## Endpoints

### `GET /api/health`

```json
{ "ok": true, "models": { "embed": "gemini-embedding-2", "describe": "gemini-3.5-flash-lite" } }
```

`models.describe` shows the default. Health reports the configured value (`DESCRIBE_MODEL` in `api/.env`).

### `POST /api/detect`

Form fields: `clip` (wav, 3.0 s), `level_db` (number, the clip's peak loudness in dBFS measured by the browser).

```json
{
  "event_id": "evt_8f2a",
  "kind": "taught",
  "label": "Door knock",
  "sound_id": "snd_3c1d",
  "confidence": 0.94,
  "description": null,
  "latency_ms": 812
}
```

- `kind` is one of `"builtin" | "taught" | "unknown" | "none"`.
  - `builtin` / `taught`: matched; `label`, `sound_id` and `confidence` are set. The frontend shows the Alert screen.
  - `unknown`: loud but unmatched; `description` is a one-line string from the describe model, Gemini 3.5 Flash-Lite by default (or `null` if the describe call failed); `label` is `null`. The frontend shows "What was that?".
  - `none`: not loud enough to describe and not matched. The frontend shows nothing.
- `confidence` is a calibrated value in [0, 1]. Built-in sound IDs start with `builtin_`.
- Every `detect` call that is not `none` is saved to history.

### `POST /api/teach`

Form fields: `name` (string, 1–40 chars), `example_1`, `example_2`, `example_3` (wav, 3.0 s each), `room` (wav, 10.0 s), `icon` (optional, one of the icon keys below).

```json
{
  "sound_id": "snd_3c1d",
  "name": "Door knock",
  "icon": "door",
  "self_check": { "passed": true, "score": 0.88, "threshold": 0.71 },
  "latency_ms": 2410
}
```

- `self_check.passed` is `false` when example 3 does not match examples 1 and 2. The frontend asks the user to re-record. The sound is still saved.

### `GET /api/sounds`

```json
{
  "sounds": [
    { "sound_id": "builtin_smoke_alarm", "name": "Smoke alarm", "icon": "alarm", "kind": "builtin", "enabled": true },
    { "sound_id": "snd_3c1d", "name": "Door knock", "icon": "door", "kind": "taught", "enabled": true }
  ],
  "latency_ms": 3
}
```

### `PATCH /api/sounds/{sound_id}`

JSON body: `{ "enabled": false }` and/or `{ "name": "Front door" }`. Returns the updated sound object plus `latency_ms`.

### `DELETE /api/sounds/{sound_id}`

Taught sounds only. Returns `{ "deleted": true, "latency_ms": 4 }`. Built-ins return 422 `bad_request`.

### `GET /api/history?since=<ISO time>&limit=<int, default 100>`

```json
{
  "events": [
    { "event_id": "evt_8f2a", "at": "2026-10-24T14:02:11Z", "kind": "taught", "label": "Door knock",
      "sound_id": "snd_3c1d", "confidence": 0.94, "description": null }
  ],
  "latency_ms": 5
}
```

Newest first. Audio is **not** stored; history holds metadata only.

### `GET /api/metrics`

Numbers for the Model Card page, written by `eval/` into `api/metrics.json` and served as-is.

```json
{
  "builtin_accuracy": { "zero_shot": 0.71, "trained": 0.89, "test_fold": 5 },
  "taught_miss_rate": 0.06,
  "false_alarms_per_hour": 0.5,
  "latency_ms_median": 1180,
  "gemini_calls_per_hour": { "gate_off": 3600, "gate_on": 42 },
  "updated_at": "2026-10-24T20:00:00Z"
}
```

The numbers above are placeholders for the fixture only. The real numbers come from `eval/`.

## Icon keys

`door`, `bell`, `alarm`, `baby`, `dog`, `kettle`, `microwave`, `phone`, `voice`, `glass`, `siren`, `water`, `generic`.

## Built-in sounds (fixed IDs)

`builtin_smoke_alarm`, `builtin_crying_baby`, `builtin_dog_bark`, `builtin_door_knock`, `builtin_glass_breaking`, `builtin_siren`.
