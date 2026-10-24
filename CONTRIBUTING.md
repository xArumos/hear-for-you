# Contributing to HearAlert

Thanks for helping. This guide works for both team members and outside contributors.

## Ground rules

- Read [`AGENTS.md`](AGENTS.md) first. It applies to humans too, and to any AI coding tool you use.
- API shapes live in [`CONTRACT.md`](CONTRACT.md). Changing them needs agreement from both the backend and frontend owners.
- Accessibility is a requirement: every alert must work without hearing it.

## Setup

Follow [`docs/SETUP.md`](docs/SETUP.md). You'll have the API and web app running locally in about 10 minutes.

## Workflow

1. Pull `main`.
2. Create a branch: team members use `p1/…` to `p4/…`; outside contributors use `fix/…` or `feat/…`.
3. Make one focused change. Commit messages follow `area: what changed` (for example `web: larger dismiss button`).
4. Run the checks:
   - Backend: `cd api && uv run pytest && uv run ruff check .`
   - Frontend: `cd web && npm run lint && npm run build`
5. Open a pull request using the checklist below. Never push to `main`.

## Pull request checklist

- [ ] Stays inside one folder, or explains why not
- [ ] Matches `CONTRACT.md` exactly (if it touches the API)
- [ ] Ran and tested locally (say how)
- [ ] No secrets, no raw audio, no new dependency without a note in `docs/DECISIONS.md`
- [ ] UI changes: works by keyboard, contrast 4.5:1, no sound-only cues

## Good first issues

- Add a new built-in sound (a class from ESC-50 plus an icon)
- Translate the UI strings (Spanish first)
- Add a high-contrast theme
- Show a "reconnecting" banner when the API is unreachable
- Export history as CSV

## Reporting bugs

Open an issue with: what you did, what you expected, what happened, browser and device, and the API log line (it includes latency, never audio).
