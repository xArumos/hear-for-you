# AGENTS.md — rules for every AI coding agent on this repo

Claude Code, Codex, Cursor, Copilot, Gemini CLI, and anything else: read this file before writing code.
It is the single source of truth. `CLAUDE.md`, `GEMINI.md` and `.github/copilot-instructions.md` only point here.

## 1. What we are building

HearAlert: a web app that turns household sounds into visual alerts for deaf and hard-of-hearing users.
A user teaches any sound from 3 examples. The app flashes an alert when it hears that sound again, and it describes loud sounds it does not recognize.
Full product context: `CONTEXT.md`. API shapes: `CONTRACT.md`. Environment: `docs/SETUP.md`.

This is a 48-hour hackathon project (Gator Hack V, Oct 23–25 2026). Prefer simple, working code over clever code.

## 2. Read before you act

1. `AGENTS.md` (this file)
2. The `AGENTS.md` inside the folder you are working in (`api/`, `web/`, `eval/`)
3. `CONTRACT.md` if your change touches anything that crosses the API boundary
4. `docs/DECISIONS.md` before changing the stack, a model, or a constant

## 3. Folder ownership — do not cross it

| Folder | Owner | What lives there |
| --- | --- | --- |
| `api/` | P1 (ML and backend) | FastAPI server, Gemini calls, detectors |
| `eval/` | P1 | Evaluation scripts and notebooks, Model Card numbers |
| `web/` | P2 (frontend) | React app: Teach, Listen, Alert, History, Model Card page |
| `data/` | P3 (data and integration) | Download scripts, embeddings, manifests (no raw audio in git) |
| `docs/` | Everyone (P4 leads the demo script) | Setup, decisions, model card, demo script |
| Root `.md` files | Everyone, via PR approved by P1, P2 or P3 (not the author) | Shared rules and contracts |

Rules:
- Only edit code inside the folder your human owns. If another code folder needs a change, write it up as a GitHub issue or a note in your PR description. Do not make the edit.
- `docs/` is shared: when your change makes a doc out of date, update it in the same PR (a dependency or decision in `DECISIONS.md`, a step in `SETUP.md`, a number in `MODEL_CARD.md`). Add or fix only what your change affects; don't rewrite other people's sections or reorganize a doc without asking the team.
- Never change `CONTRACT.md` on your own. Propose the change in the PR description; P1 and P2 must both agree.
- If you need a shape the contract does not have, stop and ask your human.

## 4. Fixed stack (see `docs/DECISIONS.md` for why)

- Backend: Python 3.12, FastAPI, Uvicorn, `google-genai` SDK, NumPy, scikit-learn, `soundfile`. Env managed by `uv`.
- Frontend: Node 22 LTS, npm, Vite, React 18, TypeScript (strict), Tailwind CSS. No other UI framework.
- Storage: SQLite via Python's `sqlite3` module. No ORM.
- Models: `gemini-embedding-2` (audio → vector) and `gemini-3.5-flash-lite` (describe unknown sounds; see `docs/DECISIONS.md`). No other models.
- Audio format everywhere: **16 kHz, mono, 16-bit PCM WAV, 3.0 s clips**. Embedding 2 accepts only mp3 or wav.

Do not add dependencies without your human's approval. Every new dependency goes into `docs/DECISIONS.md`.

## 5. Secrets and data

- The Gemini API key lives only in `api/.env` as `GEMINI_API_KEY`. Never put it in frontend code, logs, commits, or chat.
- The browser never calls Gemini directly. Every model call goes through `api/`.
- Never commit raw audio. `data/raw/` is gitignored. Commit embeddings (`.npy`) and manifests (`.csv`) only.
- ESC-50 audio is CC BY-NC. Credit it; never redistribute the clips.

## 6. Hackathon rules that affect code

- All project code must be written after Fri Oct 23, 5:00 PM ET. Do not paste in code from earlier personal projects. Open-source libraries are fine.
- Commit at least hourly with clear messages. Git history is our proof.

## 7. How to write code here

- Small, focused changes. One feature per PR.
- Match the contract exactly: field names, types, status codes, error shape.
- TypeScript: no `any`. Python: type hints on every function.
- Handle the failure path. Every Gemini call has a timeout (10 s), one retry on 429/5xx, and returns the contract's error shape on failure.
- Log one line per request with the latency in ms. No audio or keys in logs.
- No new files at the repo root without asking.
- Before you report a change as done, run it. Backend: `uv run pytest` and hit the endpoint with `curl`. Frontend: `npm run build` and click through the screen.

## 8. Accessibility is a requirement, not polish

This app is for people who may not hear. Every alert must be visual (icon + text + colour), never sound-only.
Contrast at least 4.5:1, tap targets at least 48 px, respects `prefers-reduced-motion`, keyboard operable. Details in `web/AGENTS.md`.

## 9. Git workflow

- Branch per person: `p1/<feature>`, `p2/<feature>`, `p3/<feature>`, `p4/<feature>`.
- Never push to `main` directly (GitHub blocks it). Open a PR, then merge it yourself with **Create a merge commit** (not squash) once it is ready:
  - CI is green. `.github/workflows/ci.yml` runs `uv run pytest` in `api/`, `npm ci && npm run build` in `web/`, and blocks committed audio, databases, `.env` files and API keys. Run the same commands locally first.
  - `web/package-lock.json` and `api/uv.lock` are committed and up to date (CI installs from them).
  - Root `.md` files (including `CONTRACT.md`): approved by one of P1, P2 or P3 who is not the author. `CONTRACT.md` still needs both P1 and P2.
  - Touches a folder you don't own: approved by that folder's owner.
- Commit messages: `area: what changed`, for example `api: add /teach endpoint`, `web: alert screen flash`.
- Pull `main` before starting each new task.

## 10. Integration checkpoints

Everyone stops and runs the full loop together at: **Fri 11 PM, Sat 1 PM, Sat 6 PM**. Feature freeze is **Sat 10 PM**. After that, only bug fixes.

## 11. When unsure

Ask your human. Do not guess at a product decision, invent an endpoint, or "improve" another owner's code.
