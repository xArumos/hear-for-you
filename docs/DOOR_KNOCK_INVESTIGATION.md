# Door-knock investigation — 2026-10-25 (P2)

The reported household miss cannot be assigned an exact cause without its audio or
request diagnostics. Bark success proves at least one capture/request path works;
it does not prove every short impact reaches classification. No global sensitivity,
model, microphone constraints, UI, storage, or P1-owned code was changed.

## Verified frontend correction

`api/app/detectors.py` accepts raw built-in probability > 0.6 and rounds it to two
decimals. `web/src/alert-policy.ts` previously rejected the resulting 0.60. It now
accepts 0.60, retaining enabled-category, finite-score, duplicate-ID, and background
checks. Regression tests cover knocks, barks and glass breaks. This corrects wire
rounding; it does not lower the backend classifier threshold. The boundary test
uses an explicit test value, not a measured confidence or a generated detection.

## Capture and decision trace

- AudioWorklet PCM -> 100 ms frames -> resampling to 16 kHz. No microphone
  constraint change. The gate needs about one second of baseline, then a frame RMS
  rise above the rolling median + 12 dB. A brief peak can have low frame RMS.
- The onset buffer includes 0.5 s before and 2.5 s after the onset, encoded as
  48,000-sample mono PCM16 WAV. No overlapping analysis windows. Multiple impacts
  inside the capture are included, rather than requiring separate confirmations.
- `ListeningSession` permits one in-flight request, at least one second apart;
  completed clips during an outstanding request/backoff are discarded, not queued.
  A short event cannot recur on demand after such a drop. This is a verified code
  path, not proof it affected the user's test. Consider a bounded pending-clip
  policy separately with capture-age, stop/Teach and backoff tests.
- FastAPI validates audio. The smoke-alarm rule runs before rate limiting; then
  Gemini audio embedding, enabled taught matching, and built-in top-class scoring.
  Built-ins require raw p > 0.6. There is no repeated-confirmation requirement.
- A disabled match suppresses the unknown fallback. Otherwise only peak > -20 dBFS
  and an available describe slot (once per 10 s) permit relevance description.
  Background judgement, describe failures or an occupied slot yield `none`.
- All non-smoke results go through `ongoing.py`, including knocks and glass breaks:
  repeated matches less than 10 s apart reuse an event ID. Frontend duplicate-ID
  suppression can therefore hide a distinct subsequent knock. First knocks are
  not blocked by grouping. Frontend knocks/glass/smoke need no repetition or
  category cooldown; barks/sirens/crying additionally group observations locally.
- App admission drives both visual alert state and existing local History. No
  presentation, navigation, recording, Save Sound, Check Sound or storage edit.

Door knocking is present in the contract, frontend defaults, seeded backend and
saved classifier classes. Read-only inspection and GET `/api/sounds` confirmed all
six built-ins enabled in the configured local database. This does not verify a
remote deployment or the user's browser's saved preferences.

## Recent backend changes

`1be7692`: relevance-gated unknowns, disabled-sound suppression and ongoing grouping.
`5756615`: revised relevance prompt and held-out evaluation. The prompt explicitly
includes knocking as relevant and typing/laptop/desk taps as background. Neither
introduced repeated confirmation or a higher built-in cutoff. These changes can
remove the unknown fallback (describe cap/background judgement) and suppress
subsequent event IDs, without changing built-in probabilities.

## Measured classification

Replayed the committed model on committed held-out fold-5 ESC-50 embeddings (no
Gemini network call or training). These are existing processed recordings, not
new microphone or distance tests. Counts below concern the built-in path only;
they do not include unknown fallback, enabled preferences or actual rendered UI.

| Ground truth | Samples | Correct top class | Pass backend | Frontend eligible before / after |
| --- | ---: | ---: | ---: | ---: |
| Door knock | 8 | 8 | 6 | 6 / 6 |
| Dog bark | 8 | 8 | 7 | 7 / 7 |
| Glass breaking | 8 | 8 | 8 | 8 / 8 |
| Other | 12 | 11 | 0 | 0 / 0 |

Rejected knock clips: `5-218981-A-30` p=0.494370 and `5-250026-B-30` p=0.597276;
both rank as knocking. Rejected bark: `5-9032-A-0` p=0.595486. The rounding
correction does not change these counts; do not claim it fixes all missed knocks.

Also downloaded four real recordings from the pinned official ESC-50 revision
`33c8ce9eb2cf0b1c2f8bcf322eb349b6be34dbb6` into temporary storage. Source:
https://github.com/karolpiczak/ESC-50 (Karol J. Piczak; CC BY-NC audio, no clips
committed or redistributed). IDs: knock `5-218981-A-30`, second knock
`5-218980-A-30`, bark `5-203128-A-0`, typing `5-223099-A-32`.

Live Gemini embedding + saved classifier on max-energy 3 s PCM windows:

| Clip | Peak dBFS | Top class | Probability | Built-in admitted |
| --- | ---: | --- | ---: | --- |
| Knock | -0.123 | Knock | 0.554346 | No |
| Second knock | -9.000 | Knock | 0.817653 | Yes |
| Bark | -0.927 | Bark | 0.871551 | Yes |
| Typing | 0.000 | Other | 0.732521 | No |

The rejected knock also scored glass=0.345319. Peak loudness alone is not enough.
ffmpeg is unavailable locally; used already-installed SciPy polyphase resampling,
mono PCM16 encoding and the project's max-energy window selector. These live
scores differ from stored embeddings and are not a bit-identical preprocessing
reproduction or independent held-out model validation.

Replayed the full real clips through the actual frontend SoundGate with two
seconds of silence for baseline and silence to finish pending windows. The gate
emitted 1 window for each knock, 2 for bark, 2 for typing. Silence is framing, not
a simulated target. This checks the gate on these files; it bypasses a physical
microphone, browser processing and real room noise. Gate output alone is not an
alert. Initial direct FastAPI tests admitted the max-energy rejected knock as
unknown ("A door knocker is heard.") and the second knock as builtin (0.82).
Subsequent immediately submitted bark/typing requests correctly hit 429; these are
not recognition failures. A second run spaces onset-buffered requests by 10.1 s
to exercise fallback without rate-limit interference, with temporary DB isolation.

Existing committed relevance test results (not rerun) report knock alerts 5/5,
bark 5/5, glass 5/5, typing 2/5. Both typing false alerts were described as knocks,
so a weaker cutoff is not justified from positive clips alone. The broader test
summary records 12/45 negative alerts. The 12 fold-5 "other" results above do not
establish speech/typing/tapping specificity for the whole pipeline.

No controlled loud/normal/distance labels, laptop-tapping or ordinary speech
recordings are available. No distance reliability claim. No real phone, live room
microphone or browser click-through was available in this investigation.

## P1 approval needed before backend edits

1. Add sanitized server-side diagnostic logs for all outcomes: top-class scores,
   taught/builtin/disabled decisions, fallback skip reason, rate-limit and grouping
   decisions. No audio, embeddings, keys or transcript logging; no API shape change.
   Current request logs show kind/latency but no rejected confidence/reason.
2. Exempt discrete knocks and glass breaks from the backend's ongoing grouping,
   preserving smoke bypass and sustained bark/siren/crying grouping. This fixes the
   verified distinct-event suppression path, not the first-miss confidence issue.
3. Evaluate knock-specific acceptance against real negatives before selecting any
   class-specific threshold. Two held-out knocks are correctly ranked but rejected;
   their scores alone cannot select a safe new cutoff. Keep other categories and
   global sensitivity unchanged. Overlapping windows also require measured capture
   evidence and quota/backoff tests, rather than changing all capture now.

The user requested approval before any P1 code edit; none was made.

The spaced FastAPI run on each first gate window returned HTTP 200 for all four:

| Real gate-window source | API result | Wire confidence | Frontend admission |
| --- | --- | ---: | --- |
| Knock | unknown: Someone is knocking on a door. | null | Yes |
| Second knock | builtin Door knock | 0.84 | Yes |
| Bark | builtin Dog bark | 0.89 | Yes |
| Typing | unknown: Someone is knocking on a door. | null | Yes (false alert) |

Fed these actual responses through AlertPolicy with enabled defaults. These
results are identical before/after the boundary correction (none is a 0.60 case).
Admission is the code path that sets the alert state; actual browser rendering
was not exercised. The typing result reproduces the relevance model confusion:
frontend text filtering cannot distinguish two identical knock descriptions.
No new acoustic specificity or full fix of the user's missed knock is claimed.

Validation: 36 frontend tests, TypeScript lint and production build pass; 138
backend tests pass. GET /api/sounds succeeds with knocking enabled. Source-level
checks preserve existing smoke bypass; no real smoke-alarm recording was tested.
No new dependencies. Working branch already contains fetched origin/main; no
merge was necessary. Pre-existing untracked files were left untouched.
