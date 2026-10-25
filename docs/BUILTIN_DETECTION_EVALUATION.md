# Built-in detection evaluation — 2026-10-25 (P2)

This report separates measured results from simulations and unavailable evidence.
No backend, model, threshold, data, microphone, navigation, storage or History
persistence code was changed.

## Categories and sources

The authoritative built-ins in `CONTRACT.md`, backend seed data and frontend
defaults are: Smoke alarm, Crying baby, Dog bark, Door knock, Glass breaking and
Siren. All six were enabled in `GET /api/sounds` during this run.

The classifier-backed evaluation used 16 recordings from the pinned official
ESC-50 revision `33c8ce9eb2cf0b1c2f8bcf322eb349b6be34dbb6` in temporary storage.
ESC-50 audio is CC BY-NC (Karol J. Piczak); no audio was committed or
redistributed. Five categories used two source recordings each. Six negatives
used keyboard typing, mouse clicking, footsteps, breathing, vacuum cleaner and
clock ticking.

ESC-50 has no smoke-alarm recording. The repository's smoke detector has
synthetic rule tests, but those are not real accuracy evidence. Real smoke-alarm
coverage remains unmeasured and is tracked in GitHub issue #14. Synthetic tones
were not counted as detections here.

## Method

Official 44.1 kHz recordings were decoded, converted to mono and resampled with
the already-installed SciPy polyphase resampler. The existing P3 max-energy
selector chose a three-second window. Each submitted file was exactly 48,000
samples, 16 kHz, mono, 16-bit PCM WAV. Source-amplitude cases were not normalized.

For one source per positive category, simulations produced:

- quiet: peak target -30 dBFS;
- moderate: peak target -15 dBFS;
- loud: peak target -3 dBFS;
- simulated attenuation/distance: peak target -24 dBFS;
- typing and vacuum backgrounds: event peak -12 dBFS plus background peak
  -24 dBFS;
- window position: event shifted 400 ms later, with the trailing 400 ms
  truncated rather than wrapped.

These gain, mix and timing cases are simulations from real licensed recordings.
They do not prove physical distance, another-room pickup, room reverberation or
microphone behavior. No real across-room, another-room, conversation, television,
music, fan/air-conditioning, laptop-tapping or ordinary-speech recordings were
available. Vacuum noise is not reported as a fan test.

The P2 runner in `web/scripts/evaluate-detection.ts` validated each WAV, measured
peak dBFS, submitted it to the real local `/api/detect` route, read the enabled
sound preferences and applied the production frontend `AlertPolicy`. Positives
were 1.1 seconds apart. Negatives were 10.1 seconds apart so the describe cap did
not suppress later negative cases. API audio was processed through live Gemini
embedding and the saved classifier. Input preparation bypassed the physical
microphone and onset gate.

“Correct” below means the exact expected built-in result. A meaningful unknown
description is reported separately and does not count as a correct built-in.
Repeated responses can intentionally reuse backend event IDs or be grouped by the
frontend; independent frontend eligibility was therefore also evaluated with a
fresh policy per response.

## Results

| Category | Tests | Correct built-in | Missed built-in | False alerts | Notes |
| --- | ---: | ---: | ---: | ---: | --- |
| Smoke alarm | 0 real | — | — | — | No licensed real fixture; rule tests are not accuracy evidence |
| Crying baby | 9 | 8 | 1 | 0 built-in | Vacuum mix ranked baby at 0.541858, then returned relevant unknown distress |
| Dog bark | 9 | 9 | 0 | 0 built-in | Passed every tested level, mix and timing variant |
| Door knock | 9 | 6 | 3 | 1 knock-like unknown | One source was an unknown knock; typing/vacuum mixes returned none |
| Glass breaking | 9 | 6 | 3 | 0 built-in | Simulated attenuation ranked glass at 0.587978; both background mixes ranked other |
| Siren | 9 | 7 | 2 | 0 built-in | Quiet/moderate variants ranked siren at 0.516960/0.548678 |

Across 45 positive variants, 36 (80%) were exact built-ins. This is a small,
correlated test matrix derived from ten recordings and is not a reliability
estimate. Thirty-eight of 45 were independently eligible for a meaningful
frontend alert because one rejected baby and one rejected knock were described as
relevant unknowns.

| Condition | Cases | Correct built-in |
| --- | ---: | ---: |
| Two source-amplitude recordings per category | 10 | 9 |
| Quiet, -30 dBFS peak | 5 | 4 |
| Moderate, -15 dBFS peak | 5 | 4 |
| Loud, -3 dBFS peak | 5 | 5 |
| Simulated attenuation, -24 dBFS peak | 5 | 4 |
| Typing/vacuum background mixes | 10 | 5 |
| 400 ms later window position | 5 | 5 |

Median server latency was 695 ms for baby, 699 ms for dog, 609 ms for knock,
634 ms for glass and 686 ms for siren. These local-network observations include
Gemini latency and are not end-to-end sound-to-alert latency from a microphone.

The six negative cases produced no built-in alert. Two produced relevant unknown
alerts: footsteps was described as someone knocking, and clock ticking was
described as a clock ticking. Keyboard typing, mouse click, breathing and vacuum
produced none. This negative set is too small for a false-alert rate. The typing
sample peaked at -20.042 dBFS, just below the unknown loudness cutoff. An earlier
live test documented in `DOOR_KNOCK_INVESTIGATION.md` used a different, louder
typing clip and incorrectly returned a knock description. Typing is therefore not
proven safe across recordings or levels.

Committed held-out fold-5 embeddings provide broader clean-source context:

| Category | Held-out clips | Correct top class | Pass p > 0.6 |
| --- | ---: | ---: | ---: |
| Crying baby | 8 | 8 | 6 |
| Dog bark | 8 | 8 | 7 |
| Door knock | 8 | 8 | 6 |
| Glass breaking | 8 | 8 | 8 |
| Siren | 8 | 8 | 6 |
| Other | 12 | 11 | 0 built-in alerts |

## Door-knock trace

Both source knocks previously passed the actual frontend onset gate. In this API
matrix, source 1 returned `builtin_door_knock` at 0.82. Source 2 ranked knock
highest at raw probability 0.554346 (glass 0.345319), failed the built-in cutoff,
then returned a relevant unknown knock. Quiet, moderate, loud, simulated
attenuation and shifted-window variants of source 1 were built-ins. With typing,
the top class became `other` at 0.508142 while knock scored 0.395664. With vacuum,
`other` scored 0.856633 and knock 0.063711. Both mixes returned none in the
rate-limited positive sequence.

There is no repeated-confirmation rule for a first knock in the frontend. Knocks
are eligible immediately. Backend ongoing grouping can reuse the event ID for a
separate knock inside ten seconds; a busy frontend session also drops completed
clips while another request is in flight. These ownership findings and the need
for sanitized rejection diagnostics are assigned to P1 in GitHub issue #27.

No global or class-specific threshold change is supported by this matrix. The
footstep/knock confusion and louder-typing false alert show the false-positive
tradeoff. Dog recognition remained intact.

## Frontend and regression status

- Existing tests verify disabled categories do not create new frontend alerts or
  History entries, enabled categories remain eligible, and knocks/glass/smoke need
  no frontend repetition. No preference was mutated during this evaluation.
- The integration runner stores no audio, changes no expectation to pass and
  records actual API responses. Its README explains license and simulation labels.
- Website tests, lint and production build pass. Backend tests were run read-only.
- The iOS build still requires the existing ignored `VITE_API_BASE_URL` setting;
  it was not treated as a code failure.

## Remaining evidence gaps

P3 should collect consented or appropriately licensed real smoke alarms,
conversation, laptop/desk tapping, television/music, fan/HVAC, reverberant-room
and physical-distance recordings. Results must distinguish real distance from
attenuation. This corpus handoff is assigned to P3 in GitHub issue #28. P1 owns
classifier/threshold evaluation and any backend change. P2 will not modify
`api/`, `eval/` or `data/` for these findings.
