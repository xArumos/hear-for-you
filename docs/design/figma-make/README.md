# HearAlert UI design (Figma Make export)

Design by **P4** (GitHub `zenlynwu-droid`), made in Figma Make and exported to
[zenlynwu-droid/BuildHearAlertAccessibilityApp](https://github.com/zenlynwu-droid/BuildHearAlertAccessibilityApp)
(snapshot of commit `2488e15`, Oct 24 2026).

**This folder is a visual reference, not app code.** Nothing here is built, run or tested by CI. The real app lives in
`web/` (owner: P2). Use this design for the look and the screen layouts; keep `web/`'s working audio, API and state code.

## Files

| File | What to take from it |
| --- | --- |
| `src/App.tsx` | Every screen in one file: `Listen`, `Teach`, `Recording`, `History`, `Alert` (recognized / unknown), plus `Sidebar`, `Brand` and the `Icon` set |
| `src/index.css` | Colours (`:root` variables, light + dark under `.theme-dark`), fonts (Inter, Manrope), spacing, card and button styles |
| `public/favicon.svg` | App icon |
| `index.html`, `src/main.tsx` | Figma boilerplate; nothing to copy |

The export's `package.json` (React 19, Tailwind 4, Vite 8, pnpm) was left out on purpose. Do not add its dependencies:
`web/` keeps its own stack and `package-lock.json`.

## Instructions for an AI building `web/` from this design

Read `AGENTS.md`, `web/AGENTS.md` and `CONTRACT.md` first. Where this design disagrees with them, **they win**:

1. **Styling.** Copy the colour variables from `src/index.css` into `web/src/styles/tokens.css` (light and dark) and
   use them through Tailwind. Check every text/background pair is at least 4.5:1 contrast (3:1 for large text and
   icons); adjust a shade if one fails.
2. **Icons.** Reuse the `iconPaths` SVGs from `App.tsx`. Its keys already match the contract's icon keys (`door`,
   `bell`, `alarm`, … `generic`).
3. **No stored audio.** The API never stores audio and history has no clips. Drop the playback controls, "Clip" column,
   "Delete audio" and "retained clip" text from **History** and the **Alert** screens. In **Teach**, playing back a
   recording before it is sent is fine (it is still in the browser), but nothing is kept after the request.
4. **Privacy text must be accurate.** Clips *are* sent to our server and to Google's Gemini API. Replace "Nothing is
   uploaded" and similar lines with the required wording from `web/AGENTS.md`:
   - Listen: "Only sounds louder than your room are analyzed. Audio is never stored."
   - Listen and Teach: "Not a replacement for a smoke-alarm strobe."
5. **Alert types come from the contract.** `kind` is `builtin`, `taught`, `unknown` or `none`. Use the "recognized"
   design for `builtin` and `taught` (label + confidence as a percent), the "What was that?" design for `unknown`
   (`description` may be `null`: show a fallback line), and nothing for `none`. There is no "attention" kind; drop that
   variant and the "Smoke alarm-like sound" example (the built-in classifier has no smoke-alarm training data).
6. **Alert accessibility.** Full screen, `role="alert"`, label at least 48 px, dismiss button at least 64 px tall,
   colour flash at most 3 times per second, solid colour instead of flashing under `prefers-reduced-motion`.
7. **Teach flow.** Keep the guided 3 × 3 s examples + 10 s room noise steps. After saving, show the response's
   `self_check`: if `passed` is `false`, ask the user to re-record (the sound is still saved).
8. **Real data instead of mock state.** "Your sounds" comes from `GET /api/sounds` (with enable/disable and delete),
   History from `GET /api/history`, all through `web/src/api/client.ts`. Remove the demo-only buttons ("Simulate
   reconnect", "Preview … alert") or hide them behind a dev flag.
9. **Screens the design doesn't cover:** the Model Card page (`GET /api/metrics`) and error / offline / permission
   states beyond the ones shown. Follow the same visual style.
