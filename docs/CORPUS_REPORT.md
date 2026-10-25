# Public smoke-alarm and household regression corpus

Collected on October 25, 2026 for issues #14 and #28.
The user approved public recordings with explicit physical-capture gaps.
All audio stays outside Git; this delivery publishes aligned manifests, real Gemini embeddings, provenance, validation reports and reproducible download instructions.

## Delivered data

| Dataset | Category | Three-second windows | Original recordings |
| --- | --- | ---: | ---: |
| Smoke alarm | `builtin_smoke_alarm` | 31 | 5 |
| Smoke alarm | `other`, confusers | 10 | 5 |
| Smoke alarm | `co_alarm`, evaluation only | 1 | 1 |
| Regression | Door knock | 3 | 3 |
| Regression | Keyboard typing | 9 | 3 |
| Regression | Table/board finger tapping | 8 | 3 |
| Regression | Footsteps | 8 | 3 |
| Regression | Group speech | 9 | 3 |
| Regression | Fans/extractor | 9 | 3 |
| Regression | Dog barking | 3 | 1 |
| Regression | Baby crying | 3 | 1 |
| Regression | Ambulance siren | 3 | 1 |

The smoke matrix has 42 rows and the regression matrix has 55 rows, each with 768 float32 dimensions and finite unit vectors.
All embeddings come from `gemini-embedding-2`; no mocked vectors or generated alarm audio are included.
These are correlated windows from recordings, not 97 independent trials.
Related table-tapping and fan variants are conservatively grouped, giving the regression collection 18 source groups from 21 files.
Source labels come from provider descriptions; RMS activity bounds are exploratory annotations and do not establish manually verified event counts.
The glass-breaking candidate described as cinema Foley was excluded rather than silently counted as an authentic glass-break recording.

## Training and held-out boundaries

| Smoke fold | Smoke windows | Confuser windows |
| --- | ---: | ---: |
| 1 | 5 | 1 |
| 2 | 10 | 3 |
| 3 | 3 | 2 |
| 4 | 10 | 2 |
| 5 | 3 | 2 |

The CO/T4 recording has an empty fold and is not a smoke-positive training example.
Every original recording and its derivatives stay in one fold.
Unequal original durations make these clip counts unequal; breaking source groups to balance counts would leak data between folds.
P1 should train on folds 1-4, hold fold 5 out, exclude empty folds, and inspect the small per-fold class counts before choosing a calibration protocol.
The regression dataset has no assigned training folds and no detected overlap with the committed ESC-50 and smoke sources.
Unknown upstream reuse and shared recording sessions cannot be ruled out from filenames and hashes alone.
Model retraining, classifier-loader changes and evaluation metrics remain P1's work.

## Sources and restoration

BigSoundBank recordings are by Joseph Sardin and explicitly offered under [CC0](https://bigsoundbank.com/licenses.html).
The smoke examples include its [first](https://bigsoundbank.com/smoke-detector-alarm-s0800.html), [second](https://bigsoundbank.com/smoke-detector-alarm-2-s1151.html) and [third](https://bigsoundbank.com/smoke-detector-alarm-3-s1153.html) smoke-detector recordings.
The smoke collection also includes [Smoke Alarm Sound](https://www.freesoundslibrary.com/smoke-alarm-sound/) credited to Spanac / Free Sounds Library under CC BY 4.0.
[SpliceSound's neighboring-room alarm](https://freesound.org/people/SpliceSound/sounds/369847/) is CC0 and is explicitly described as heard through a neighboring room.
Its distance in meters and capture device remain unknown.
The alarm and mrrap4food's microwave-button recording use an attribution-preserving public Git mirror because the original media CDN returned 403.
The source catalog pins that mirror to a Git commit and records the separate original source, author, license receipt, media URL and SHA-256.
The microwave's original page was inaccessible during acquisition; its CC0 attribution receipt is the pinned mirror's `public/test-audio/SOURCES.md`.
Every used recording's credit and actual media variant is retained in `data/public_corpus_sources.json` and the published metadata companion.

```bash
uv run --project data python data/fetch_public_corpus.py --dataset all
```

Restoration verifies original audio hashes and prepares deterministic generation manifests without making Gemini requests.
Already present, valid originals are reused without downloading.
Changed upstream bytes fail instead of silently changing the dataset.
The published conversions were produced with FFmpeg 9.0.1.
Restoration also compares the prepared manifest and provenance against the published bundle, so decoder drift fails visibly before stale embeddings are reused.
Follow [the embedding gate and replay instructions](CORPUS_COLLECTION.md) to rebuild or replay the collection.
Teammates can also validate the committed matrices without downloading audio; the validator then explicitly reports `audio_verified=false`.

## Measured browser findings

A real public smoke-alarm recording was replayed digitally through the production frontend microphone gate and real backend.
With the documented `gemini-3.5-flash-lite` description model, the app returned `kind=unknown`, displayed "An alarm is beeping." and added one matching local and backend History event.
The description request's server latency was 3,199 ms; this is not end-to-end sound-to-alert latency.
The smoke-specific rule did not recognize that recording; its dominant tone was approximately 2,492 Hz, and none of 19 sampled three-second windows passed the rule.
This identifies a reproducible P1 follow-up, not a validated threshold fix.
An earlier run used a stale local `gemini-3.8-flash` override, received two HTTP 503 responses from description calls, and produced no alert.
The successful rerun changed only the test process's model environment, not saved configuration or application code.
This recording is part of the delivered smoke collection, so this diagnostic is not a new independent held-out recognition estimate.

## Remaining coverage and acceptance

No new physical phone captures, measured across-room distances, controlled closed-door trials, or microphone comparisons were performed.
No gain attenuation or mixing is presented as physical-distance evidence.
The speech recordings contain groups or crowds; controlled one-to-one conversation remains missing.
TV/music, authentic glass breaking, low-frequency 520 Hz smoke alarms, measured reverberation and known alarm-model diversity remain gaps.
The provider-reported neighboring-room alarm supplies one useful source condition, not a distance reliability rate.
No false-alerts/hour, recognition accuracy, calibrated confidence claim or household-wide reliability claim is made.
Artifact completion is distinct from collection completeness; quality reports keep these missing conditions visible.
P1/P2 should review the source and annotation limitations before consuming the data for training or interpreting replay outcomes.
Issue #28's public-data delivery does not close its future physical-capture work, and #14's downstream classifier training is not included in this PR.
