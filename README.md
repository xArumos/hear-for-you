# Hear For You

**Sound awareness for deaf and hard-of-hearing people.** Teach Hear For You any sound from three examples (your door knock, your dog, your kettle) and it flashes a visual alert when it hears that sound again. When something loud happens that it doesn't recognize, it tells you what it heard in plain words.

Built in 48 hours at [Gator Hack V](https://gatorhack2026.devpost.com/) (UF AI Days 2026).

> Hear For You is not a certified life-safety device. It does not replace a smoke-alarm strobe or bed shaker.

<!-- TODO (P4): add a demo GIF here -->

## Why

About 430 million people worldwide have disabling hearing loss. Phone sound-recognition features exist, but Apple's custom sounds only cover electronic beeps, and neither Apple's nor Google's tells you about sounds it doesn't know. Hear For You learns any sound, runs in any modern browser, and describes the unknown.

## How it works

1. The browser listens and only sends audio when the level jumps above the room's normal noise (the **loudness gate**). Silence never leaves the device.
2. Each loud moment becomes a 3-second clip, sent to our API.
3. [Gemini Embedding 2](https://ai.google.dev/gemini-api/docs/embeddings) (GA April 2026) turns the clip into a vector in the same space as text.
4. Our detectors match it against built-in sounds and the sounds you taught.
5. A match triggers a full-screen alert. A loud sound with no match goes to Gemini 3.5 Flash-Lite for a one-line description.

Evaluation numbers are on the in-app **Model Card** page and in [`docs/MODEL_CARD.md`](docs/MODEL_CARD.md).

## Quick start

You need Python 3.12 with [uv](https://docs.astral.sh/uv/), Node 22, and a free [Gemini API key](https://aistudio.google.com/apikey).

```bash
cp api/.env.example api/.env        # then paste your key into api/.env
cd api && uv sync && uv run uvicorn app.main:app --reload --port 8000
cd web && npm install && npm run dev  # in a second terminal
```

Open the URL Vite prints. Phones need HTTPS for the microphone; see [`docs/SETUP.md`](docs/SETUP.md).

## Repo layout

| Folder | What's inside |
| --- | --- |
| `api/` | FastAPI server, Gemini calls, detectors |
| `web/` | React + Vite app |
| `eval/` | Evaluation scripts that produce the Model Card numbers |
| `data/` | Download scripts, manifests, embeddings (no raw audio) |
| `docs/` | Setup, decisions, model card, demo script |

## Contributing

We'd love help. Start with [`CONTRIBUTING.md`](CONTRIBUTING.md) and issues labelled `good first issue`.

## Credits and licences

- Code: [MIT](LICENSE).
- Built-in sound training data: [ESC-50](https://github.com/karolpiczak/ESC-50) by Karol J. Piczak, licensed **CC BY-NC**. Clips are not redistributed in this repo; run `data/` scripts to download them.
- Models: Gemini Embedding 2 and Gemini 3.5 Flash-Lite via the Gemini API.

## Team

<!-- TODO (P4): names and roles -->
