# Frontend microphone regressions

Run `npm test` for isolated lifecycle, WAV, gate and teach-state tests. These tests
use microphone doubles and never call Gemini.

`browser-microphone.mjs` uses Chrome's DevTools protocol and Node's built-in
WebSocket, with no additional packages. Start an **isolated test Chrome profile**
with remote debugging (do not point it at a personal profile):

```sh
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new \
  --remote-debugging-port=9223 --user-data-dir=/tmp/hear-for-you-browser-tests \
  --no-first-run --autoplay-policy=no-user-gesture-required about:blank
```

With the backend and `npm run dev` running, from `web/`:

```sh
node tests/browser-microphone.mjs
```

Override `BROWSER_DEBUG_PORT` or `FRONTEND_URL` for another debugger or preview
server. The suite runs against a generated browser audio stream. It checks all
four independent review/acceptance steps, selected re-recording, playable WAVs,
resource release, distinct device/permission errors, exact API form fields and
sample counts, failed saves/self-checks, Listen OFF/Start/Stop, rapid Stop and late
permission grants, detection onset, stale responses and disabled categories.
Teach/detect/PATCH responses are controlled in the test browser; this does not
verify Gemini availability. Test storage is removed at the end. Do not run this
suite in a browser profile containing personal sound metadata.

## Manual hardware verification

1. In external Chrome and Safari, open `http://localhost:5173` (development), then
   repeat on `http://localhost:4173` after building and starting preview. Verify
   there is no microphone prompt on load or merely navigating to Listen.
2. Teach before starting Listen: record three real sounds and quiet room noise.
   Check every clip stays in review, playback is audible, Re-record replaces only
   its selected slot, and acceptance advances exactly one step. Reject microphone
   access once, then enable it in site settings and retry. Disconnect the device
   during capture if possible; the error should identify interruption/device loss.
3. Confirm Save stays unavailable until all four clips are accepted. Save with the
   backend running; verify the self-check result. A network failure must preserve
   the recordings for retry. The contract has no separate check-only endpoint;
   the existing Save and check action explicitly saves through `/api/teach`.
4. Start Listen; verify the browser's microphone indicator and active state. Make
   a louder sound after normal room noise; verify real backend recognition and
   history. Disable/re-enable a category in Your Sounds and repeat. Stop listening,
   navigate to Teach, and reload: capture must stop, no new detections may appear,
   and listening must remain OFF until started again.
5. Check keyboard playback/review controls, phone layout, and the existing theme.
   A phone needs the documented HTTPS tunnel; LAN HTTP cannot grant microphone
   access. Neither physical microphone/speaker behavior nor Safari is covered by
   the generated-audio Chrome regression suite.

## Gemini failure regression

With the same isolated Chrome debugger and frontend running, run:

```sh
node tests/browser-gemini-errors.mjs
```

This sends generated browser audio through the real onset gate and returns a
controlled HTTP 502 upstream error. It checks that an opaque non-retryable Gemini
failure stops listening, releases microphone tracks, produces no false alert, and
does not keep issuing requests. Unit tests cover bounded exponential backoff,
server retry delays, quota/authentication/model failures and recovery.

These tests do not certify credentials or call Gemini. A successful `/api/health`
also does not verify Gemini authentication. After changing `api/.env`, the backend
owner must restart the existing backend to reload its startup settings. The
contract exposes one explicit `/api/teach` save-and-self-check operation, not a
separate check-only endpoint.


## Alert relevance regression and distance checks

With an isolated Chrome debugger and frontend running, execute
`node tests/browser-alert-policy.mjs`. It uses generated onset audio and controlled
API responses; it checks background-only speech, amplitude-only unknowns and low
scores create neither alerts nor local History entries, while a single glass
break and a doorbell mixed with speech create both. It does not measure acoustic
recognition accuracy. `npm test` also checks continued-event grouping, rearming,
enabled settings, taught voice cues, malformed scores and mixed descriptions.

For real testing, use approved prerecorded audio at safe playback levels. Include
keyboard typing, laptop taps, mouse clicks, conversation, footsteps, fans and
ordinary household noise as negatives. Play doorbells, dog barks, microwave tones,
smoke-alarm recordings, sirens and safe prerecorded glass breaks as positives;
include new takes of taught sounds and each target mixed with conversation.
Repeat at measured near, doorway and another-room positions on each target phone
and laptop. Keep gain, playback level and settings fixed; note microphone device,
distance, door position, room noise, sample source and repetitions. Do not induce
real hazards or record/commit raw microphone clips.

For each trial, record expected category, API result, admitted alert, time to
alert and local History count. Count negative trials with alerts as false
positives and positive trials without a correct alert as false negatives. Count
wrong-category alerts separately as both a missed target and a false category.
Repeat sustained recordings and distinct events inside/outside the grouping gap.
Check disabled categories and subsequent re-enabling. Inspect backend History
separately: the frontend cannot undo its pre-existing insertion on /detect.
No house-wide or distance accuracy is established by the synthetic browser tests.


## Listening across pages

With the isolated Chrome debugger and frontend running, execute
`node tests/browser-global-listening.mjs`. It opens and closes its own test tab,
uses generated microphone audio and controlled API responses, and checks:

- OFF on load/reload; one capture across Home, Your Sounds, History, Teach, Login
  and Listen; returning shows the actual active state.
- Actual onset capture produces the existing alert and local History off Listen.
- Teach recording/review releases detection capture, preserves a valid three-second
  recording, and resumes prior listening on leaving the recording screen.
- Playback previews temporarily suspend detection so teaching audio cannot alert.
- Disabled categories stay suppressed off Listen; Stop releases tracks and ignores
  pending API responses; a device interruption changes global status to OFF.

Unit tests also cover pending permission grants, serialized teardown/reacquisition,
recording cancellation handoff, API retry limits and preview/recording overlap.
This is browser-generated audio, not physical microphone or Gemini validation.

On physical desktop and phone browsers (including Safari), start listening and
navigate every page without additional permission prompts. Trigger a safe, known
sound while viewing History or Your Sounds and check the alert and one History
entry. Return to Listen and stop; verify the browser microphone indicator turns
off. Repeat with Teach capture, preview playback, cancellation and an initial
listening state of OFF. Confirm only previously enabled listening resumes. Revoke
microphone permission, disconnect the device, lock the screen or switch tabs and
check the reported state when returning; if the browser interrupts capture,
restart explicitly. Browser/OS restrictions still apply outside the visible site.
No styling, microphone gain or detection thresholds changed.
