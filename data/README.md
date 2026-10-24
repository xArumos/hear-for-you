# data/ — datasets, recordings, embeddings (owner: P3)

Read the root `AGENTS.md` first. **No raw audio is ever committed.** `data/raw/` is gitignored.

## Layout

```
data/
  raw/                 # gitignored: ESC-50 download, our recordings
  manifests/           # committed: one CSV row per clip (path, label, fold, source)
  embeddings/          # committed: .npy arrays aligned row-for-row with a manifest
  download_esc50.py
  convert.py           # any audio → 16 kHz mono 16-bit WAV, cut to 3.0 s windows (uses ffmpeg)
  embed_esc50.py       # embeds the manifest's clips with gemini-embedding-2 at 768 dims
  embed_recordings.py  # same for our venue recordings
```

## ESC-50 → built-in sounds

| HearAlert built-in | ESC-50 class |
| --- | --- |
| `builtin_dog_bark` | `dog` |
| `builtin_crying_baby` | `crying_baby` |
| `builtin_door_knock` | `door_wood_knock` |
| `builtin_glass_breaking` | `glass_breaking` |
| `builtin_siren` | `siren` |
| `builtin_smoke_alarm` | none in ESC-50; use `clock_alarm` as a stand-in and record real smoke-alarm test beeps |
| other | all remaining 44 classes |

ESC-50 clips are 5 s; `convert.py` takes the loudest 3.0 s window of each.

## Our recordings (Saturday 8–9 AM)

| Set | Count | Notes |
| --- | --- | --- |
| Desk bell | 20 takes | Different distances and angles |
| Door knock (a real door) | 20 takes | Name the door in the manifest |
| Kettle or microwave beep | 20 takes | |
| Background, no target sounds | 60 min | TV, kitchen, conversation, venue noise; cut into 3.0 s windows |

Manifest columns: `clip_id, path, label, source (esc50 | ours), fold, recorded_at, device`.

## Embedding rules

- Embed once; commit the `.npy` and the manifest together in one commit.
- Batch slowly to respect free-tier limits (about 1 request per second). Resume from the last row if interrupted.
- Store float32, L2-normalized, 768 dims.

## Licences

ESC-50 is CC BY-NC (ESC-10 subset CC BY). Credit it in the README; never redistribute clips. Our recordings stay private to the team.
