"""Export full chronological WAVs to a private, self-contained browser replay bundle."""
from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path

from corpus import read_prepared, overlap, require
from dataset_io import DATA, ROOT, sha256_file, write_json


def export(manifest: Path, destination: Path, output_dir: Path = DATA,
           trial_ids: list[str] | None = None) -> None:
    read_prepared(manifest, "regression")
    require(destination.resolve().is_relative_to((output_dir / "raw").resolve()), "Replay bundles contain audio and must stay under data/raw.")
    metadata = json.loads(manifest.with_name("regression_metadata.json").read_text())
    leakage = overlap(manifest, "regression", output_dir)
    shared = set(leakage["shared_sources"])
    require(not trial_ids or set(trial_ids) <= metadata["sources"].keys(), "Unknown trial ID in replay selection.")
    trials = []
    for identifier, source in sorted(metadata["sources"].items()):
        if trial_ids and identifier not in trial_ids:
            continue
        path = ROOT / source["replay_path"]
        require(path.is_file() and sha256_file(path) == source["replay_sha256"], f"{identifier}: restore unchanged chronological replay WAV.")
        trials.append({"trial_id": identifier, "expected_label": source["label"],
                       "capture_kind": source["capture_kind"], "windowing": source["windowing"],
                       "source_group": source["source_group"], "events": source["events"],
                       "duration_seconds": source["duration_seconds"],
                       "held_out_eligible": identifier not in shared and source["capture_kind"] != "simulation",
                       "condition": {k: source[k] for k in ("device", "room", "distance_m", "position", "door_position", "background")},
                       "audio_sha256": source["replay_sha256"],
                       "wav_base64": base64.b64encode(path.read_bytes()).decode("ascii")})
    write_json(destination, {"version": 1, "evidence": "digital_microphone_replay", "manifest_sha256": sha256_file(manifest),
                             "overlap": leakage, "trials": trials})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--output-dir", default=DATA, type=Path)
    parser.add_argument("--trial-id", action="append", help="Replay only selected original IDs; repeat to select several.")
    args = parser.parse_args()
    try:
        export(args.manifest, args.output, args.output_dir, args.trial_id)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(1, f"Replay export stopped: {exc}\n")


if __name__ == "__main__":
    main()
