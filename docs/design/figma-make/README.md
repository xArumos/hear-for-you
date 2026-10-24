# Hear For You UI design (Figma Make export)

Design by **P4** (GitHub `zenlynwu-droid`), made in Figma Make and exported to
[zenlynwu-droid/BuildHearAlertAccessibilityApp](https://github.com/zenlynwu-droid/BuildHearAlertAccessibilityApp)
(snapshot of commit `457c024`, Oct 24 2026; first copied at `2488e15`).

To refresh after P4 pushes again: copy the same files from her repo's latest commit, update the commit above, and
re-check the notes below against the new design.

**This folder is a visual reference, not app code.** Nothing here is built, run or tested by CI. The real app lives in
`web/` (owner: P2). Use this design for the look and the screen layouts; keep `web/`'s working audio, API and state code.

## Files

| File | What to take from it |
| --- | --- |
| `src/App.tsx` | Every screen in one file: `Home`, `Listen`, `Teach`, `Recording`, `MySounds`, `History`, `Alert` (recognized / unknown), plus `Sidebar`, `Brand` and the `Icon` set. Also `AuthScreen` and `Account` (see note 11) |
| `src/index.css` | Colours (`:root` variables, light + dark under `.theme-dark`), fonts (Chillax, Satoshi, Inter, Manrope), spacing, card and button styles |
| `public/favicon.svg` | App icon |
| `index.html`, `src/main.tsx` | Figma boilerplate; nothing to copy |

The export's `package.json` (React 19, Tailwind 4, Vite 8, pnpm) was left out on purpose. Do not add its dependencies:
`web/` keeps its own stack and `package-lock.json`.

### Fonts: never commit the Chillax or Satoshi files

`index.css` loads `Chillax-Regular.woff` and `Satoshi-Medium.woff` from `/fonts/`. Those files were **left out**: both are
Indian Type Foundry fonts ("All rights reserved", licence at fontshare.com/terms). The Fontshare licence allows free use
in websites and apps but forbids redistributing the files, including uploading them to a public server, and this repo
is public. So:

- Load them from Fontshare's servers instead, with a stylesheet link like
  `https://api.fontshare.com/v2/css?f[]=chillax@400&f[]=satoshi@500&display=swap` (confirm the exact URL on the fonts'
  Fontshare pages), and delete the two `@font-face` blocks.
- Credit the fonts somewhere visible, e.g. the Model Card page: "Chillax and Satoshi by Indian Type Foundry
  (Fontshare)". The licence asks for this.
- Inter and Manrope come from Google Fonts (open licence); the existing `@import` is fine.

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
10. **App name: "Hear For You".** The team renamed the app (Oct 24). Use "Hear For You" and the motto "Here when it
    matters. Hearing what matters." in the UI, as the design does. Code names stay as they are (repo `hearalert`,
    `/api/...` paths, IDs); the rest of the docs may still say "HearAlert" until they're updated.
11. **No accounts.** The design's sign-in, create account, verify email, reset password, session-expired screens and
    the Account page are not supported: the API has no users or auth endpoints, and adding them is out of scope. Don't
    build them and don't gate anything behind sign-in. Show My Sounds and History to everyone. Drop the "Requires
    sign-in" labels.
12. **My Sounds** maps to `GET /api/sounds` (list, including the six built-ins), `PATCH /api/sounds/{id}` (rename,
    enable/disable) and `DELETE /api/sounds/{id}` (taught sounds only; built-ins can only be disabled). The API keeps
    no training recordings, so drop the per-sound recording list and "up to five training recordings". A sound is
    taught from exactly **3 examples + 10 s of room noise**.
13. **Home page** is fine as a landing screen. Remove the "Prototype · simulated data" badge once screens use real
    data, and point "Get started" at Teach instead of account creation.
14. **History** now shows labels and times only, which matches the API. Its filters can be done client-side or with
    `since`; drop the "Attention" type as in note 5.
