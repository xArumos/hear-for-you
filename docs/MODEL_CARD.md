# Model Card — HearAlert detectors

Numbers here are filled in by `eval/` (P1) and must match `api/metrics.json` and the in-app Model Card page. Replace every `TBD` with a measured value and the date it was measured.

## What the models do

| Model | Input | Output | Trained on |
| --- | --- | --- | --- |
| Zero-shot baseline | Clip embedding | Closest text label ("the sound of a door knock") | Nothing (uses Gemini Embedding 2's shared audio-text space) |
| Built-in classifier | Clip embedding | One of 6 built-in sounds or "other" | ESC-50 folds 1–4 |
| Personal detector | Clip embedding | Match / no match for each taught sound | The user's 3 examples + 10 s room noise |

Embeddings come from `gemini-embedding-2` at 768 dimensions. All three models are ours; Gemini supplies the embeddings only.

## Results

| Metric | Value | How measured | Date |
| --- | --- | --- | --- |
| Built-in accuracy, zero-shot | TBD | ESC-50 fold 5, 6 classes + other | |
| Built-in accuracy, trained | TBD | ESC-50 fold 5 | |
| Built-in accuracy, our own recordings | TBD | Clips recorded at the venue | |
| Taught-sound miss rate | TBD | 20 new takes each of 3 taught sounds | |
| False alarms per hour | TBD | 60 min of TV, kitchen and conversation audio | |
| Median sound-to-alert latency | TBD | Onset timestamp to alert render | |
| Gemini calls per hour, gate off → on | TBD → TBD | Same 60 min background audio | |

## Known limitations

- ESC-50 has a known leakage issue (some clips were pre-processed in class-dependent ways), so fold accuracy may be optimistic. That is why we also report accuracy on our own recordings.
- Few-shot detectors are weak in rooms much noisier than where they were taught.
- Phone microphones differ; loudness is relative, not calibrated dB.
- Audio is sent to the Gemini API for embedding; only gated clips, never stored by us.

## Intended use

Awareness aid at home. **Not** a life-safety device; does not replace certified alarm strobes or bed shakers.

## Data credits

ESC-50 by Karol J. Piczak, CC BY-NC. Clips are not redistributed.
