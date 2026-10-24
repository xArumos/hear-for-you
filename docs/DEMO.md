# DEMO.md — video, live pitch, and backup

## Props checklist

- [ ] Desk bell (the sound we teach live)
- [ ] Laptop A: runs the app (listener)
- [ ] Laptop B: same app in demo mode (`VITE_DEMO_MODE=1`), cached results
- [ ] Bluetooth speaker with kitchen noise and a glass-breaking clip
- [ ] Phone hotspot (in case venue Wi-Fi drops)
- [ ] USB stick with the video

## 3-minute video

| Time | Beat | Shows |
| --- | --- | --- |
| 0:00–0:20 | A knock goes unanswered. "For 430 million people, this happens every day." | Impact |
| 0:20–0:50 | Teach the desk bell: 3 rings, 10 seconds | Design |
| 0:50–1:20 | Kitchen noise plays, nothing fires. Bell rings, screen flashes "Desk bell, 94%" | Technical execution |
| 1:20–1:40 | Glass breaks. "What was that? Glass breaking." + Teach this sound | Gemini, Best AI Hack |
| 1:40–2:10 | Why it's new: Embedding 2 (Apr 2026), audio and text in one space. Model Card numbers | ML, recency |
| 2:10–2:35 | Difficulties: rate limits → loudness gate; latency; iPhone limits | Challenge requirement |
| 2:35–3:00 | Limits and privacy; not a smoke-alarm replacement; open-source repo | Presentation, Open Source |

Record by **Sun 1:00 PM**. Upload unlisted; test the link in an incognito window.

## Live pitch (Monday 10:15 AM, if top 10)

2 minutes. Roles: one speaks, one runs Laptop A, one holds the bell.

1. Problem in one sentence.
2. Teach the bell on stage.
3. Play noise (nothing fires), ring the bell (alert).
4. One line on how it works and the Model Card numbers.
5. Limits and next step (native app, on-device).

If anything fails, switch to Laptop B without comment and keep talking.

## Questions to rehearse

- *Doesn't the iPhone already do this?* Only electronic sounds, only Apple devices, and it ignores sounds it doesn't know.
- *Why cloud, not on-device?* Embedding 2 is what makes 3-example teaching and descriptions work; the gate keeps silence private. On-device is next.
- *Isn't this just an API call?* The detectors, thresholds, gate and evaluation are ours. Show the Model Card.
- *Did you talk to deaf users?* Answer honestly; quote anyone we reached.
