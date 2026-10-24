# web/AGENTS.md — frontend rules (owner: P2)

Read the root `AGENTS.md` and `CONTRACT.md` first. The browser never calls Gemini.

## Layout

```
web/
  src/
    api/client.ts        # the ONLY place that calls fetch('/api/...'); typed from CONTRACT.md
    api/types.ts         # TypeScript types mirroring CONTRACT.md exactly
    fixtures/            # one JSON file per contract response; used when VITE_USE_FIXTURES=1
    audio/recorder.ts    # getUserMedia + AudioWorklet → Float32 PCM
    audio/wav.ts         # resample to 16 kHz mono, encode 16-bit PCM WAV
    audio/gate.ts        # loudness gate: rolling room baseline, onset detection
    hooks/useWakeLock.ts # request on Listen, re-request on visibilitychange
    screens/             # Teach, Listen, Alert, WhatWasThat, History, ModelCard
    components/
    styles/tokens.css    # colour, type, spacing tokens (light + dark)
  vite.config.ts         # proxy /api → http://localhost:8000
```

## Audio rules

- Record raw PCM through an AudioWorklet. Do not upload `MediaRecorder` output: it is webm/mp4, which the API rejects.
- Every clip sent is exactly 3.0 s (48,000 samples at 16 kHz), mono, 16-bit WAV. Room clip: 10.0 s.
- The gate keeps a rolling baseline of the room's level (median of the last 10 s). When the level rises above baseline + 12 dB, capture 0.5 s before and 2.5 s after the onset, then send.
- Send `level_db` (the clip's peak in dBFS) with every `/detect` call.
- Never send more than one `/detect` per second. On 429, wait `retry_after_ms`.

## Alert rules (accessibility is the product)

- Every alert = icon + text label + colour flash. Never rely on sound or colour alone.
- Alert screen: full-screen, label at least 48 px, confidence shown as a percent, dismiss button at least 64 px tall.
- `prefers-reduced-motion`: replace flashing with a solid colour change.
- Flash at most 3 times per second (photosensitive-seizure guidance).
- Vibration: call `navigator.vibrate` only if it exists (Android). iPhone has no vibration API.
- Contrast at least 4.5:1 for text, 3:1 for large text and icons. Tap targets at least 48 × 48 px.
- Everything keyboard operable with visible focus rings. Alerts are announced with `role="alert"`.
- Show the privacy line on Listen: "Only sounds louder than your room are analyzed. Audio is never stored."
- Show the safety line on Listen and Teach: "Not a replacement for a smoke-alarm strobe."

## Code rules

- TypeScript strict, no `any`. Types come from `api/types.ts`, which mirrors `CONTRACT.md` field for field.
- Components never call `fetch` directly; use `api/client.ts`.
- Tailwind for styling; colours only from `styles/tokens.css`.
- Handle every state: loading, empty, error, offline ("Reconnecting…" banner), permission denied.

## Before a PR

`npm run lint && npm run build`, then click through the changed screen on desktop and on a phone over the HTTPS tunnel.

## Don't

- Don't put the API key, or any Gemini call, in the browser.
- Don't add a UI library or state library. React state and context are enough.
- Don't add "Add to Home Screen" prompts (Wake Lock breaks in iOS home-screen apps).
