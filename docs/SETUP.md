# SETUP.md — one environment for everyone

Every teammate follows these steps exactly, so code that runs on one Linux machine runs on all four.

## 1. Install the tools (once)

| Tool | Version | Install |
| --- | --- | --- |
| Git | any recent | `sudo apt install git` (or your distro's equivalent) |
| uv | latest | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Python | 3.12 | `uv python install 3.12` (uv manages it; no system Python needed) |
| Node | 22 LTS | via [nvm](https://github.com/nvm-sh/nvm): `nvm install 22 && nvm use 22` |
| ffmpeg | any | `sudo apt install ffmpeg` (used by data scripts to convert audio) |
| cloudflared | latest | [Cloudflare Tunnel download](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/) (HTTPS for phones) |

Check: `uv --version && node --version && ffmpeg -version | head -1`.

## 2. Get the code

```bash
git clone https://github.com/xArumos/hearalert.git
cd hearalert
```

## 3. Secrets

1. Create a free key at [Google AI Studio](https://aistudio.google.com/apikey). Each person uses their own key, so rate limits are not shared.
2. `cp api/.env.example api/.env` and set `GEMINI_API_KEY=...`.
3. Never commit `api/.env`. It is in `.gitignore`.

`api/.env.example` contents:

```
GEMINI_API_KEY=your-key-here
EMBED_MODEL=gemini-embedding-2
DESCRIBE_MODEL=gemini-3.8-flash
EMBED_DIM=768
MAX_DETECT_PER_SEC=1
DB_PATH=./hearalert.db
```

## 4. Run the backend

```bash
cd api
uv sync
uv run uvicorn app.main:app --reload --port 8000
```

Check: `curl localhost:8000/api/health` returns `{"ok": true, ...}`.

## 5. Run the frontend

```bash
cd web
npm install
npm run dev
```

Vite serves on `http://localhost:5173` and proxies `/api` to port 8000.
To build against fixtures without the backend: `VITE_USE_FIXTURES=1 npm run dev`.

## 6. Test on a phone (microphone needs HTTPS)

```bash
cloudflared tunnel --url http://localhost:5173
```

Open the `https://…trycloudflare.com` URL it prints on the phone. On iPhone, use Safari in the browser. Do **not** "Add to Home Screen": Wake Lock does not work there.

## 7. Data (P3 runs this once, then shares embeddings through git)

```bash
cd data
uv run python download_esc50.py     # into data/raw/ (gitignored)
uv run python embed_esc50.py        # writes data/embeddings/esc50_768.npy + manifest.csv
```

## 8. AI coding tools

All tools read the same rules:

| Tool | Reads |
| --- | --- |
| Claude Code | `CLAUDE.md` → imports `AGENTS.md` |
| Codex, Cursor, most others | `AGENTS.md` |
| Gemini CLI | `GEMINI.md` → points to `AGENTS.md` |
| GitHub Copilot | `.github/copilot-instructions.md` |
| Chat AIs in a browser | Paste `CONTEXT.md` (and `CONTRACT.md` for API work) |

Start every AI session with: *"Read AGENTS.md and <folder>/AGENTS.md, then …"*.

## 9. Before every task

```bash
git checkout main && git pull
git checkout -b pN/<feature>
```

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `429 RESOURCE_EXHAUSTED` | Your key hit the free-tier limit. Wait a minute, or check limits at aistudio.google.com/rate-limit |
| Mic permission never appears on phone | You're on `http://`. Use the cloudflared HTTPS URL |
| `bad_audio` from the API | Clip is not 16 kHz mono 16-bit WAV of 3.0 s; check `web/src/audio/wav.ts` |
| Screen sleeps during Listen | Wake Lock was released (tab hidden). The app re-requests on return; keep the tab in front |
