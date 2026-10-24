# data/ - datasets, recordings, embeddings (owner: P3)

Read the root `AGENTS.md` first.
All original and converted audio, downloads, checkpoints, and smoke-test outputs stay in ignored `data/raw/`.
Commit the completed embedding matrix and its manifest together; never commit audio or secrets.

## Product purpose and class selection

This dataset supports HearAlert's built-in classifier and its rejection of unrelated sounds as `other`.
It supplies classifier inputs, not measured detection accuracy or real-world false-alarm rates.
Training, calibration, thresholds, and evaluation belong to P1 in `eval/`.
Smoke-alarm recognition needs separate recordings and is deliberately excluded from this dataset.

| HearAlert label | ESC-50 category | Clips |
| --- | --- | --- |
| `builtin_dog_bark` | `dog` | 40 |
| `builtin_crying_baby` | `crying_baby` | 40 |
| `builtin_door_knock` | `door_wood_knock` | 40 |
| `builtin_glass_breaking` | `glass_breaking` | 40 |
| `builtin_siren` | `siren` | 40 |
| `other` | 44 categories excluding the five above and `clock_alarm` | 60 |

Use the original ESC-50 folds: train on 1-4, test on 5, and never tune on fold 5.
The 60 negatives have exactly 12 clips per fold, with no duplicate clips.
Selection uses Python's `random.Random(42)` with sorted inputs.
Within each fold, choose a category uniformly among the least-used eligible categories globally, then a clip uniformly from that category and fold.
A category is chosen at most once within each fold.
This covers all 44 negative categories, with one or two clips per category.
Do not interpret this small negative sample as representative of an hour of household background noise.

## Reproducibility and layout

Upstream: [Karol Piczak's ESC-50](https://github.com/karolpiczak/ESC-50).
Pinned revision: `33c8ce9eb2cf0b1c2f8bcf322eb349b6be34dbb6`.
The downloader validates archive paths and CRCs, metadata class/fold counts, original WAV format, and local originals against the pinned archive.
It downloads the official archive once and extracts only metadata and the 260 selected originals.
Reruns reuse validated downloads and converted WAVs whose source, preprocessing version, and output hash match.
Allow about 700 MB of disk space for the archive, selected originals, and converted clips.

```text
data/
  raw/esc50-<revision>.zip     # official archive, ignored
  raw/esc50/meta/esc50.csv    # original metadata, ignored
  raw/esc50/audio/            # selected original clips, ignored
  raw/converted/              # 3.0 s WAVs and conversion hashes, ignored
  raw/embedding-cache/        # validated vector checkpoints and smoke receipt, ignored
  raw/smoke/<dataset>/        # five-row manifest, matrix and validation, ignored
  manifests/esc50.csv         # 260 rows, committed with the completed matrix
  embeddings/esc50_768.npy    # (260, 768), float32, unit vectors
  download_esc50.py
  convert.py
  embed_esc50.py
  embedding_core.py          # shared API, checkpoints, gates and reports
  dataset_io.py              # shared manifests and atomic writes
  prepare_recordings.py
  embed_recordings.py
  validate_dataset.py
  recordings.example.csv     # example inputs, not real collected data
  tests/
  pyproject.toml
  uv.lock
```

Manifest columns are exactly `clip_id,path,label,source,fold,recorded_at,device`.
`clip_id` is the upstream filename stem; `path` is relative to the repository root and points to a converted WAV.
`source` is `esc50`; recording dates and devices are blank because they are unavailable.
Rows are ordered by numeric fold, HearAlert label, and clip ID.
Matrix row `i` always corresponds to manifest row `i`, excluding the header.
The embedder verifies this manifest against the deterministic upstream selection before making requests.

## Setup and five-clip gate

Install ffmpeg and uv, then run these commands from the repository root.
The data project uses Python 3.12 and only the approved NumPy and `google-genai` dependencies, with a separate lockfile.

```bash
uv sync --project data --locked
uv run --project data python data/download_esc50.py --smoke-test
uv run --project data python -m unittest discover -s data/tests -v
uv run --project data python data/embed_esc50.py --smoke-test --dry-run
```

The downloader's smoke option creates the full deterministic manifest but converts only five clips, one per built-in label from training folds.
Conversion decodes/resamples through ffmpeg to 16 kHz mono signed PCM16, then chooses the exact 48,000-sample window with maximum squared amplitude energy.
Energy is accumulated in int64 to avoid PCM16 overflow; ties select the earliest window.
No gain normalization is applied.
Corrupt, silent, truncated, and shorter-than-three-second clips fail before embedding.
Standalone conversion is also available:

```bash
uv run --project data python data/convert.py input.wav data/raw/example.wav
```

Set `GEMINI_API_KEY` privately in `api/.env` before the live test.
This offline data script is explicitly authorized to call Gemini directly; the browser still never receives the key.
The script reads only that key and does not print it or load arbitrary shell commands from the file.

```bash
uv run --project data python data/embed_esc50.py --smoke-test
uv run --project data python data/embed_esc50.py --smoke-test
```

The first run must produce a `(5, 768)` float32 matrix with finite unit vectors, using `gemini-embedding-2` at 768 dimensions.
The second run must report `newly_embedded=0`, proving checkpoint reuse without needing a client or key.
A successful cache-only smoke rerun writes a gate receipt tied to the current manifest and the five audio/model/preprocessing fingerprints.
The full embedder refuses to run without this receipt and matching valid checkpoints.

After the real smoke test and cache-only rerun succeed, prepare the remaining audio and run the full batch:

```bash
uv run --project data python data/download_esc50.py
uv run --project data python data/embed_esc50.py --full --dry-run
uv run --project data python data/embed_esc50.py --full
```

## API pacing, failures, and recovery

Each request contains one WAV and asks for `output_dimensionality=768`, without label text or an unsupported task type.
Request starts are at least one second apart, including retries.
Each request has a 10-second timeout and at most one explicit retry on 429 or 5xx; SDK retries are disabled.
The retry honors a longer `Retry-After` header or Gemini `RetryInfo.retryDelay`.
Authentication errors, timeouts, invalid responses, and exhausted retries stop the run with successful checkpoints preserved.
Logs include clip ID, attempt, status, and latency, never audio or key contents.
An exclusive process lock prevents ESC-50 and recording embedding jobs from running together.
Persisted request timing also preserves the one-second gap across process restarts.
Run offline embedding when the live app is not using the same key; the backend has its own limiter.

Each checkpoint is atomically saved under a fingerprint of clip ID, SHA-256 of the converted WAV, model, dimensionality, and preprocessing version.
Cached vectors must be finite float32 arrays of shape `(768,)` and have L2 norm within `1e-5` of one.
Changed inputs or invalid checkpoints are embedded again.
Rerun the same command after an interruption; valid completed clips require no new request.
All inputs are validated before any billable request, and each file is checked again before publication.
Only one clip is retained in memory at a time while embedding continuous recordings.
The full matrix is written atomically only after all 260 embeddings succeed, so a failed run never publishes a partial matrix.
No fallback model or synthetic vectors are substituted if Gemini is unavailable.

Offline tests cover exact window selection, ties, overflow, ffmpeg conversion, bad audio, deterministic negative selection, fold preservation, unsafe archives, manifest alignment, normalization, retry timing, checkpoint recovery, and the full-run gate.
They make no network requests and incur no Gemini usage.

## Collecting our recordings

| Set | Count | Notes |
| --- | --- | --- |
| Desk bell | 20 takes | Different distances and angles |
| Door knock (a real door) | 20 takes | Name the door in the manifest |
| Kettle or microwave beep | 20 takes | |
| Background, no target sounds | 60 min | TV, kitchen, conversation, venue noise; cut into 3.0 s windows |

No additional audio is needed to finish the five-class ESC-50 dataset.
These local recordings are needed to measure behavior on the actual door, appliance, microphone, and room.
Smoke-alarm recordings are deferred; this dataset does not establish smoke-alarm detection.

Record individual takes for at least three seconds, with one target sound per take and no overlapping target sounds.
Use separate files and unique clip IDs; vary distance, microphone angle, and room conditions across the 20 takes.
Record background continuously during representative activity without deliberately triggering the target sounds.
Keep original files, private input metadata, and long room recordings under `data/raw/ours/`.
Do not upload them to GitHub.
The audio may be WAV or another format ffmpeg can decode; conversion produces the required WAV format.

Copy `data/recordings.example.csv` into `data/raw/recordings.csv` and replace every example with actual paths, dates, and devices.
The example dates and devices are illustrative, not recording evidence.
Paths are relative to the repository root; absolute local paths also work, provided they are inside the allowed raw directory.
Use exactly the standard seven columns, `source=ours`, an empty `fold`, an ISO 8601 recording start time with a timezone, and a device description.
Supported labels are `builtin_door_knock`, `desk_bell`, `appliance_beep`, and `background`.
The bell, appliance, and background labels are evaluation labels, not new built-in sound IDs.

## Preparing and embedding local recordings

```bash
uv run --project data python data/prepare_recordings.py --input data/raw/recordings.csv
uv run --project data python data/embed_recordings.py --smoke-test --dry-run
uv run --project data python data/embed_recordings.py --smoke-test
uv run --project data python data/embed_recordings.py --smoke-test
uv run --project data python data/embed_recordings.py --full --dry-run
uv run --project data python data/embed_recordings.py --full
uv run --project data python data/validate_dataset.py --dataset recordings
```

Preparation uses the loudest three seconds of each sound take.
It streams background PCM to disk and then emits consecutive, non-overlapping three-second windows, retaining quiet windows that contain nonzero samples.
Wholly silent windows are excluded and counted; the final fragment shorter than three seconds is discarded and its duration recorded.
A silent sound take is rejected rather than silently removed from the positive examples.
Preparation fails clearly for missing metadata, duplicate IDs, unsupported labels, corrupt files, or audio shorter than three seconds.
An empty input or a collection with no usable windows does not replace previous outputs.
For isolated testing, `--output-dir` changes the output workspace and `--raw-dir` changes the allowed source directory.

Outputs are `manifests/recordings.csv`, `manifests/recordings_metadata.json`, `reports/recordings_quality.json`, and eventually `embeddings/recordings_768.npy`, relative to the output workspace.
The prepared manifest is sorted by clip ID and uses UTC segment times, the original device, `source=ours`, and an empty fold.
Companion metadata includes the parent clip ID, source SHA-256, grouping ID, segment offset in samples and seconds, preprocessing version, and converted-audio hash.
The grouping ID is the original source hash, so duplicate source files remain grouped even if their filenames differ.
Quality reports include accepted duration, silent exclusions, discarded trailing duration, source counts, and collection-target deficits.
Only accepted background duration is available for downstream false-alarm calculations; excluded silence and trailing fragments must not inflate the scored duration.

The smoke selection covers every supplied label first, then fills to five clips in manifest order.
At least five prepared clips are required; a successful smoke test and cache-only rerun gate the full run.
Fingerprints invalidate affected checkpoints when audio or preprocessing changes.
Changing source audio creates a new preparation generation without overwriting files belonging to the previous generation.
Failed or interrupted embedding runs retain successful checkpoints and never publish partial matrices.

## Verification and P1 handoff

```bash
uv run --project data python data/validate_dataset.py --dataset all
```

Completed embedding runs write `reports/esc50_validation.json` or `reports/recordings_validation.json`.
Reports bind the manifest, array, recording companions, and ordered clip fingerprints using SHA-256 and record dimensions, dtype, unit-norm range, label counts, and represented duration.
The validator checks those bindings and checks audio fingerprints when the complete audio set is available locally.
Teammates can validate committed artifacts without downloading private audio; the result then states `audio_verified=false`.
A partially missing local audio set is an error, not a successful audio verification.
Current validation summaries are written under ignored `raw/status/`; incomplete artifacts result in a nonzero exit code and an explanation.
A technically complete embedding job does not imply collection targets or product evaluation targets have been met.

P1 can load a completed dataset from the repository root as follows:

```python
import csv
from pathlib import Path
import numpy as np

name = "esc50"  # or "recordings"
with Path(f"data/manifests/{name}.csv").open(newline="") as handle:
    rows = list(csv.DictReader(handle))
X = np.load(f"data/embeddings/{name}_768.npy", allow_pickle=False)
assert X.dtype == np.float32 and X.shape == (len(rows), 768)
y = np.asarray([row["label"] for row in rows])
train = np.asarray([row["fold"] in {"1", "2", "3", "4"} for row in rows])
test = np.asarray([row["fold"] == "5" for row in rows])
```

Run the validator before loading artifacts and keep manifest row order unchanged.
ESC-50 uses folds 1-4 for training and fold 5 for final evaluation.
Local recordings are evaluation inputs by default and have no assigned folds.
If P1 later defines a training split, keep each parent recording and source-hash group entirely within one split; adjacent background windows are not independent examples.
Do not report bell or appliance-beep clips as built-in classifier accuracy; use them for personal-detector evaluation with P1's explicit enrollment/held-out protocol.
Commit each completed matrix, its manifest, validation report, and recording companion files together.
Generated test audio and mocked vectors are confined to temporary test workspaces and never published as real data.

The data tests make no live model requests:

```bash
uv run --project data python -m unittest discover -s data/tests -v
```

They exercise preparation and embedding CLIs through interruption, resume, cache-only rerun, full publication, and verification, plus metadata rejection, source changes, silence/trailing accounting, report tampering, and process locking.

## Licences and attribution

ESC-50 is by Karol J. Piczak, *ESC: Dataset for Environmental Sound Classification*, ACM Multimedia 2015, DOI [10.1145/2733373.2806390](https://doi.org/10.1145/2733373.2806390).
The dataset is [CC BY-NC 3.0](https://creativecommons.org/licenses/by-nc/3.0/); the ESC-10 subset is CC BY.
Retain this attribution, use the data under its licence, and never redistribute the clips through this repository.
Our recordings stay private to the team.
