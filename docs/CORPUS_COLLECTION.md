# Smoke-alarm and household regression collection

These instructions address issues #14 and #28 for P3.
The tooling produces data artifacts, not a replacement classifier or a claim of real-world reliability.
P1 owns model training and P2 owns frontend changes.

## Current evidence and collection targets

The initial local inventory on October 25 contained ESC-50 audio only; no personal recordings were supplied.
The public collection now provides 42 smoke-corpus windows and 55 regression windows from 32 public source files.
See [the collection report](CORPUS_REPORT.md) for counts, known failures, provenance and remaining coverage gaps.
Run `python data/inventory_corpus.py` with the data environment to refresh the private inventory under `data/raw/status/`.
Inventory entries do not establish permission to use a file.
The candidate list in `data/source_candidates.csv` is research, not a downloaded corpus or an attribution claim for a used asset.
[SpliceSound's smoke-alarm recording](https://freesound.org/people/SpliceSound/sounds/369848/) has a verified CC0 source page, but original downloading requires a Freesound login.
No credentials or consent evidence belong in Git.
The pinned, downloadable collection is described by `data/public_corpus_sources.json`.
Two attributed Freesound recordings use a public Git mirror pinned to a commit because the original media CDN returned 403.
The original source URLs, authors, license receipts, mirror URLs and audio hashes remain separate metadata fields.

For #14, aim for 30-40 smoke-alarm windows and at least ten confuser windows, representing at least five source groups per training label so all five folds have coverage.
Multiple windows from one recording do not create independent examples.
Include different alarm models, rooms, T3 variants and low-frequency recordings where available.
Record microwave/oven tones, phone alarms, kettle whistles and buzzers as `other`, with their identity in `event_variation`.
Label CO/T4 recordings `co_alarm`; the entire related group remains evaluation-only with an empty fold.
Report remaining model, room, low-frequency and CO coverage gaps alongside the source counts.

For #28, the first capture matrix is five independent takes of each of door knocks, typing, desk tapping, footsteps and ordinary speech at each of near, across-room and another-room positions.
Use one primary capture device for this matrix and write its exact model in every row.
Measure approximate meters instead of inferring distance from signal amplitude.
Then collect at least five source groups for each remaining built-in, TV/music, fan/AC, reverberant rooms and sustained conditions.
Keep background-only continuous recordings so downstream false-alert rates can use elapsed scored duration.
These small samples are exploratory, not evidence of household-wide reliability.

## Recording checklist

1. Get consent from every recorded speaker and document team reuse permission privately.
   Use a non-sensitive consent reference in the public metadata.
2. Keep microphone gain, playback volume and app settings fixed within a comparison.
   Record device, room alias, door position, background, measured distance, time and event variation.
3. Leave at least two seconds of actual room sound before the first event and at least three seconds after the last event.
   Make each independent take a separate source file and annotate event onset times relative to that file.
4. For brief events, record separate takes and multiple variations.
   For sustained sounds, capture at least 15 seconds and mark `windowing=sustained`.
   For continuous background, mark `windowing=continuous` and keep the complete original.
5. Record direct physical sounds when practical.
   Use safe prerecorded glass breaks and alarms for playback trials; never create hazards or trigger a building alarm.
   A phone playing an alarm is `speaker_playback`, not a direct alarm capture.
6. Preserve the source recording ID for public originals, playback ancestors and simulated mixes in `source_group` and `lineage`.
   Related session takes should share a group if they cannot honestly be considered independent.
   Never split duplicate recordings or derivatives across training and evaluation.

## Input metadata

Copy `data/corpus.example.json` into ignored `data/raw/` and replace all placeholders.
The template deliberately fails validation until a real file, permission and event annotations are supplied.
Use `null` for genuinely unavailable metadata, not invented timestamps, distances or device names.
Use a different input JSON for each dataset.

Supported capture kinds are `direct_capture`, `speaker_playback`, `public_recording` and `simulation`.
The smoke-alarm training corpus rejects simulations.
Private audio requires `license=consented-private`, `consent_status=granted` and a non-sensitive `consent_ref`.
Public audio requires a verified CC0-1.0, CC-BY-3.0 or CC-BY-4.0 license, source URL, author, attribution and actual download date.
Retain the source page/license evidence privately at download time and review the actual audio before admitting it.
All metadata in a published companion is public; use room and collector aliases rather than identifying information.

Each event annotation has `at_seconds`, `sound_id` and boolean `expected_alert`.
Use the existing built-in sound ID for a known target, or `null` for an expected unknown event.
An ordinary negative recording may have an empty `events` list.
Unknown alarm patterns must say `unknown`; CO/T4 must never be relabeled as smoke.
Record a known alarm model in optional `alarm_model`, otherwise leave it null.
For sustained smoke training recordings, annotate `end_seconds` as well as each event onset; baseline-only windows are excluded rather than labeled as smoke.
Optional boolean `reverberant` records a known room condition.

The seven-column CSV interface remains `clip_id,path,label,source,fold,recorded_at,device`.
Each version-1 companion is keyed by original ID in `sources` and converted clip ID in `clips`.
It records permission and conditions, original and replay hashes, ordered events, crop offsets, windowing and dataset role.
The quality report separates source groups, capture types, collection deficits and artifact validity.
The `source` CSV value records the capture kind for these new corpora; existing datasets retain their current values.

## Preparation, embedding and publication

Run from the repository root using the Python environment installed for `data/`.
No new dependency is needed beyond the existing ffmpeg, NumPy and Gemini SDK.

```bash
uv run --project data python data/prepare_corpus.py --dataset smoke_alarm --input data/raw/smoke_alarm.json
uv run --project data python data/prepare_corpus.py --dataset regression --input data/raw/regression.json
```

Preparation prints the generation-specific manifest path under ignored `data/raw/prepared/`.
Use that exact path as `MANIFEST` below and choose the corresponding `DATASET`.

```bash
DATASET=smoke_alarm
MANIFEST=data/raw/prepared/smoke_alarm/REPLACE_WITH_GENERATION/smoke_alarm.csv
uv run --project data python data/embed_corpus.py --dataset "$DATASET" --manifest "$MANIFEST" --smoke-test --dry-run
uv run --project data python data/embed_corpus.py --dataset "$DATASET" --manifest "$MANIFEST" --smoke-test
uv run --project data python data/embed_corpus.py --dataset "$DATASET" --manifest "$MANIFEST" --smoke-test
uv run --project data python data/embed_corpus.py --dataset "$DATASET" --manifest "$MANIFEST" --full --dry-run
uv run --project data python data/embed_corpus.py --dataset "$DATASET" --manifest "$MANIFEST" --full
uv run --project data python data/validate_dataset.py --dataset "$DATASET"
```

At least five usable clips are required for the embedding gate.
The second smoke run must report `newly_embedded=0` before a full run is allowed.
Existing timeouts, one retry, pacing, exclusive lock and fingerprinted checkpoints apply.
Run offline jobs while the live app is not using the same key.
Failed embedding attempts leave previous published artifacts untouched and preserve successful checkpoints.
Preparation rejects missing permissions, bad annotations, invalid/short/silent sources and duplicate IDs.
Continuous/sustained embedding windows are non-overlapping; wholly silent windows and trailing fragments are reported separately.
Full chronological replay WAVs retain silence, timing and trailing fragments.
No gain normalization is applied.
For the public smoke collection, retain the highest-energy non-overlapping three-second windows with a per-source cap.
Public regression negatives retain chronological windows with a per-source cap; all complete recordings remain available for replay.
The catalog's `max_windows` and `window_selection` fields record this selection explicitly.
RMS-derived activity bounds and provider categories are exploratory annotations, not manually verified event counts.

Full publication writes the aligned manifest and companions under `data/manifests/`, the float32 unit-vector matrix under `data/embeddings/`, and the hash-bound validation report under `data/reports/`.
Commit those files together only after local validation.
The manifest is published last; an interrupted filesystem publication is detected by hash validation and must be rerun before committing.
Never commit original, converted or replay audio, private input metadata, browser profiles, or replay bundles.

## Real frontend replay and physical trials

Export a prepared or published regression manifest to an ignored bundle:

```bash
uv run --project data python data/export_corpus_replay.py --manifest data/manifests/regression.csv --output data/raw/regression-replay.json
```

Use a disposable Chrome profile, Node 22, a real frontend with `VITE_USE_FIXTURES` unset, and a backend using a separate test database.
For example, set `DB_PATH=/tmp/hear-for-you-corpus.db` when starting Uvicorn.
The runner makes real `/detect` calls and can spend Gemini quota and write backend History.
Never point it at a teammate's active demo instance.

```bash
google-chrome --remote-debugging-port=9223 --user-data-dir=/tmp/hear-for-you-corpus-chrome --autoplay-policy=no-user-gesture-required
node data/replay_corpus.mjs data/raw/regression-replay.json data/raw/regression-results.json
```

On macOS use `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome` in place of `google-chrome`.
The runner opens its own tab, substitutes only the microphone stream, and leaves API responses real.
It replays each uncropped recording at normal speed without inserting an artificial baseline.
It records requests/errors, visible alerts, local History, request absence, expected events, candidate latency and incorrect API categories.
Multiple-event latency requires manual event-to-alert matching; candidate latency is never automatically presented as accuracy.
Use repeated `--trial-id ORIGINAL_ID` options on the exporter to select a documented subset without cropping or altering its recordings.
The isolated tab resets local History/settings for every source and closes afterward.
Set `CORPUS_SCREENSHOTS=1` to save one alert screenshot per source alongside the private results.
Backend grouping persists between trials, so the runner waits eleven seconds between sources and requires a separate database.
Digital replay is explicitly labeled `digital_microphone_replay` and never establishes new physical-distance evidence.
Physical capture conditions describe how the source was recorded, not the replay transport.

For manual physical trials, use the same source ID as `trial_id` and record the fields in `data/physical_trials.example.csv`.
Run the actual microphone with the app visible; log expected event, backend result/event ID, visible alert and local History count before/after.
Measure latency from the annotated physical event, and record errors or absence of a gate request rather than inventing a detection.
Repeat with the category disabled, then re-enabled, recording both API outcome and visible outcome.
Include sustained recordings and distinct events with gaps below and above ten seconds.
Preserve counts for missed targets, wrong categories, false alerts and backend failures separately.
Only compute false alerts/hour from complete continuous background trials with their full scored duration; do not use a collection of isolated negatives as a time denominator.

## Handoff and issue completion

P1 receives the smoke-alarm matrix, manifest, provenance, grouped folds and validation report.
P1 must explicitly extend its existing ESC-50-only loader, exclude empty-fold CO evaluation rows, retrain and report held-out results in its own code folder.
Fold assignment is deterministic for the complete source inventory; freeze and version that inventory before P1 trains because additions can rebalance folds.
The current source-group constraint produces unequal clip counts across smoke folds; report those counts and do not split a source merely to equalize them.
P2 receives the regression replay bundle through private transfer, runner instructions and physical trial records.
Transfer originals and chronological WAVs privately with repository-relative layout intact so teammates can reproduce replays.
The corpus exporter flags detected training-source overlap as ineligible for held-out claims.
Overlap checks use declared lineage and available source hashes; undisclosed upstream reuse cannot be ruled out.

Artifact validation can pass while collection remains incomplete.
Review `collection.target_deficits`, overlap findings and `ready_for_issue_closure` separately.
`collection_ready_for_review` indicates sufficient collection coverage without known source overlap; automated artifact checks always leave issue closure false pending P1/P2 acceptance.
Do not close #14 until P1 can consume sufficient real data, or #28 until P1/P2 reproduce trials and review the documented coverage gaps.
New physical captures and consent require a teammate; missing inputs must remain incomplete.

Run the offline suite with `uv run --project data python -m unittest discover -s data/tests -v`.
Synthetic audio and mocked vectors exist only in temporary test workspaces and are never published as collected evidence.
