# Model Card — Hear For You detectors

Numbers here are filled in by `eval/` (P1) and must match `api/metrics.json` and the in-app Model Card page. Replace every `TBD` with a measured value and the date it was measured.

## What the models do

| Model | Input | Output | Trained on |
| --- | --- | --- | --- |
| Zero-shot baseline | Clip embedding | Closest text label ("the sound of a door knock") | Nothing (uses Gemini Embedding 2's shared audio-text space) |
| Built-in classifier | Clip embedding | One of 5 built-in sounds or "other" | ESC-50 folds 1–4 |
| Smoke-alarm rule | Raw audio | Smoke alarm or not | Nothing: checks for the standard T3 beep pattern (ISO 8201 / NFPA 72) at ~2.5–4 kHz or 520 Hz |
| Personal detector | Clip embedding | Match / no match for each taught sound | The user's 3 examples + 10 s room noise |
| Unknown-sound gate | Raw audio of a loud, unmatched clip | A one-line description and a relevant / background flag | Nothing: `gemini-3.5-flash-lite` with our prompt (`RELEVANCE_PROMPT` in `api/app/gemini.py`) |

Embeddings come from `gemini-embedding-2` at 768 dimensions. The first four detectors are ours; Gemini supplies the embeddings only. The unknown-sound gate is Gemini's own judgement, steered by our prompt; it has no calibrated confidence.

## Results

| Metric | Value | How measured | Date |
| --- | --- | --- | --- |
| Built-in accuracy, zero-shot | TBD | ESC-50 fold 5, 6 classes + other | |
| Built-in accuracy, trained | 0.865 with the p > 0.6 rule `/detect` uses (0.962 top class); 0 of 12 "other" clips fired an alert | ESC-50 fold 5, 52 clips, 5 built-ins + other (`eval/results/builtin_summary.csv`) | 2026-10-24 |
| Built-in accuracy, our own recordings | TBD | Clips recorded at the venue | |
| Smoke-alarm rule, real alarms | TBD | Real smoke-alarm recordings (issue #14). Synthetic T3 alarms with noise: detected in every 3 s window | |
| Taught-sound miss rate | TBD | 20 new takes each of 3 taught sounds | |
| Unknown gate + pipeline, background clips that would alert | 12 of 45 (27%) held-out ESC-50 clips of typing, mouse clicks, footsteps, clock ticks, breathing, vacuum, washing machine, sipping, toothbrushing. 2 of the 12 are the built-in classifier (footsteps → door knock); the rest are the relevance flag. Dev set, before the prompt revision: 14 of 45 | `eval/eval_relevance.py test` (`eval/results/relevance_test_summary.csv`); assumes every clip is loud. Before this gate, every loud unmatched clip alerted | 2026-10-24 |
| Unknown gate + pipeline, misses | 2 of 30 target clips (glass, siren, knock, alarm clock, baby, dog, car horn, church bells), 1 of 16 targets mixed with typing or footsteps at equal loudness. Both target misses are car horns | Same run, same clips held out from the classifier and the prompt revision | 2026-10-24 |
| Door knocks: lower knock-only cutoff? | No. Every cutoff below 0.6 adds false knocks on dev data, almost all footsteps (0.6: 35/96 knocks, 5/361 false; 0.5: 43/96, 10/361). Typing, mouse clicks, clapping, laughing and coughing caused 0 false knocks at any cutoff. Retraining with household clips as "other" and noisy knocks as knock makes the same trade on dev (39/96 knocks, footsteps 23/31 ignored) and loses glass breaking (29→27/32). Fold 5, for reference: 8/24 knocks at 0.6, 6/8 clean | `eval/eval_knock.py` (`eval/results/knock_*.csv`): dev = ESC-50 folds 1–4 scored out-of-fold, plus 185 household clips and 64 knocks mixed under them at 0/−6 dB; fold 5 reported only | 2026-10-25 |
| False alarms per hour | TBD | 60 min of TV, kitchen and conversation audio | |
| Median sound-to-alert latency | TBD | Onset timestamp to alert render | |
| Gemini calls per hour, gate off → on | TBD → TBD | Same 60 min background audio | |

## Known limitations

- ESC-50 has a known leakage issue (some clips were pre-processed in class-dependent ways), so fold accuracy may be optimistic. That is why we also report accuracy on our own recordings.
- ESC-50 has no smoke alarms, so smoke alarms are caught by a rule for the standard T3 pattern instead of the classifier. It is not yet measured on real recordings. Alarms that use another pattern (older continuous-beep alarms, CO alarms) are missed, and a beep that copies T3 exactly within 3 s (some microwaves) would trigger it.
- Few-shot detectors are weak in rooms much noisier than where they were taught.
- Phone microphones differ; loudness is relative, not calibrated dB.
- The unknown-sound gate is a model judgement, not a probability. Taps, typing and footsteps are often heard as knocking (most remaining false alerts), car horns are sometimes called traffic background, and the description can name the wrong source. Measured on 91 ESC-50 clips, not on real homes, microphones or distances.
- `confidence` for taught sounds maps the learned threshold to 0.5; it is not a calibrated probability.
- Doorbells and microwave or appliance tones are not built-in classes: teach them, or rely on the unknown-sound gate.
- A disabled sound is suppressed only when its own detector matches. If the detector misses it, the clip can still reach the unknown-sound gate and alert as a relevant unknown.
- Repeated detections of one sound within 10 s of each other are one history event, so a long event shows its start time only. Smoke alarms, door knocks and glass breaking are never grouped: each detection is its own alert.
- Door knocks: 5 of 40 clean ESC-50 knocks score under the 0.6 gate (all 40 rank knock first), and knocks under equal-volume background noise are rarely ranked as knocks at all (11 of 40). Footsteps are the main sound mistaken for knocking. Those knocks can still alert through the unknown-sound gate ("Someone is knocking on a door"). Real knocks at real distances are not measured yet.
- Audio is sent to the Gemini API for embedding; only gated clips, never stored by us.

## Intended use

Awareness aid at home. **Not** a life-safety device; does not replace certified alarm strobes or bed shakers.

## Data credits

ESC-50 by Karol J. Piczak, CC BY-NC. Clips are not redistributed.
