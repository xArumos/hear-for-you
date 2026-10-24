# CONTEXT.md — product context

Paste this file into any chat-based AI (ChatGPT, Gemini, Claude in a browser) before asking it for help on HearAlert.
Agents working inside the repo also read `AGENTS.md`.

## One-line pitch

HearAlert learns any sound from three examples, including the ones Apple can't, and tells you what it heard even when it has never heard it before.

## The problem

About 430 million people worldwide have disabling hearing loss (WHO). They miss door knocks, appliance cues, and people calling their name.
Apple Sound Recognition and Google Sound Notifications exist, but:
- Apple's custom sounds are limited to electronic sounds (alarms, appliances, doorbells) and need 5 recordings in a quiet room.
- Both ignore sounds they do not recognize.
- Each works on one platform only.

## Who it is for

- **Primary:** a deaf or hard-of-hearing adult at home, living alone or with hearing roommates.
- **Secondary:** anyone in situational hearing loss (headphones on, asleep, loud work).

## What makes it different

1. **Teach any sound in 3 examples:** a knock on *your* door, *your* dog, your kid calling. Not just beeps.
2. **"What was that?":** when a loud sound matches nothing taught, Gemini describes it in one line and offers to teach it.
3. **Runs in any modern browser,** including an old tablet left on the counter.

## Screens

1. **Teach:** name a sound, record 3 × 3 s examples, record 10 s of normal room noise. Self-check shows whether example 3 matches 1 and 2.
2. **Listen:** calm full-screen view, live level meter, the list of sounds being listened for, a privacy line.
3. **Alert:** full-screen colour flash, big icon, label and confidence, large dismiss button. Vibration on Android; flash only on iPhone.
4. **What was that?:** a one-line description of an unknown loud sound plus a "Teach this sound" button with the clip pre-filled.
5. **History:** today's timeline; each event can be replayed.
6. **Model Card:** our evaluation numbers (for judges).

## How it works

Browser mic → loudness gate (only sends audio when the level jumps) → 3 s WAV clip → our FastAPI server → Gemini Embedding 2 turns it into a vector → our detectors compare it against built-in sounds and taught sounds → alert, or Gemini 3.8 Flash describes it if it is loud and unknown.

## Why this counts as "fresh off the frontier"

- `gemini-embedding-2` went GA on April 22, 2026. It puts audio and text in one vector space, which is what makes 3-example teaching and zero-shot matching work.
- `gemini-3.8-flash` went GA on September 2, 2026 and describes unknown sounds.

## What the ML is (ours, not the API's)

1. Zero-shot baseline: compare audio vectors to text vectors such as "the sound of a door knock".
2. Built-in classifier: logistic regression on ESC-50 embeddings for 6 built-in sounds plus "other".
3. Few-shot personal detector: a prototype per taught sound, rejected if closer to room noise; threshold tuned by leave-one-out.

Metrics that matter: miss rate, **false alarms per hour**, sound-to-alert latency, and Gemini calls saved by the gate.

## What it is not

Not a certified life-safety device. It does not replace a smoke-alarm strobe or bed shaker. Say this in the UI and the pitch.

## Honest limitations

- Audio leaves the device (only loud clips, never stored server-side). Apple's and Google's run on device.
- Browser limits: the screen must stay on (Wake Lock); iPhone browsers cannot vibrate.
- Free-tier rate limits cap how many sounds per minute we can check.

## Prizes we are targeting

Overall, Best Social Impact, Best Use of ML (DSI), Best Use of Gemini (MLH), Best Design, Best Open Source (MLH), Best Beginner Hack (if eligible).
