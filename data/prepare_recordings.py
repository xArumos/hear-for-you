"""Prepare private sound takes and continuous background for evaluation."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

import numpy as np

from convert import BACKGROUND_VERSION, PREPROCESS_VERSION, RATE, SAMPLES, loudest_start, validate_wav, write_pcm_wav
from dataset_io import DATA, ROOT, atomic_bytes, manifest_bytes, portable_path, read_csv, sha256_file, write_json

LABELS = {"builtin_door_knock", "desk_bell", "appliance_beep", "background"}


def timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("recorded_at must be an ISO 8601 timestamp with a timezone.") from None
    if parsed.tzinfo is None:
        raise ValueError("recorded_at must include a timezone.")
    return parsed.astimezone(timezone.utc)


def read_sources(path: Path, raw_dir: Path) -> list[dict[str, str]]:
    rows = read_csv(path)
    identifiers = set()
    raw_root = raw_dir.resolve()
    for row in rows:
        identifier = row["clip_id"]
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", identifier) or identifier in identifiers:
            raise ValueError("clip_id must be unique, 1-80 letters, digits, underscores or hyphens.")
        identifiers.add(identifier)
        if row["source"] != "ours" or row["fold"] != "":
            raise ValueError("Local sources require source=ours and an empty fold.")
        if row["label"] not in LABELS or not row["device"].strip():
            raise ValueError("Use a supported label and provide the recording device.")
        timestamp(row["recorded_at"])
        source = (ROOT / row["path"]).resolve()
        if not source.is_relative_to(raw_root) or not source.is_file():
            raise ValueError(f"{identifier}: source must be an existing local file inside the raw directory.")
    return sorted(rows, key=lambda row: row["clip_id"])


def decode_pcm(source: Path, target: Path) -> None:
    """Stream ffmpeg output to disk, never retain continuous audio in memory."""
    try:
        with target.open("wb") as output:
            result = subprocess.run(
                ["ffmpeg", "-nostdin", "-v", "error", "-i", str(source), "-map", "0:a:0",
                 "-ac", "1", "-ar", str(RATE), "-c:a", "pcm_s16le", "-f", "s16le", "pipe:1"],
                stdout=output, stderr=subprocess.PIPE, timeout=300, check=False,
            )
    except FileNotFoundError:
        raise ValueError("ffmpeg is required to prepare recordings.") from None
    if result.returncode or target.stat().st_size % 2:
        raise ValueError(f"{source.name}: ffmpeg could not decode complete PCM16 audio.")


def prepare(input_csv: Path, output_dir: Path = DATA, raw_dir: Path | None = None) -> list[dict[str, str]]:
    output_dir = output_dir.resolve()
    raw_dir = (raw_dir or output_dir / "raw").resolve()
    sources = read_sources(input_csv, raw_dir)
    original_hashes = {row["clip_id"]: sha256_file(ROOT / row["path"]) for row in sources}
    identity = json.dumps({"sources": sources, "hashes": original_hashes,
                          "sound_version": PREPROCESS_VERSION, "background_version": BACKGROUND_VERSION}, sort_keys=True)
    generation = hashlib.sha256(identity.encode()).hexdigest()[:20]
    destination_dir = output_dir / "raw/recordings/converted" / generation
    destination_dir.mkdir(parents=True, exist_ok=True)
    manifest = []
    clips = []
    source_reports = []
    with tempfile.TemporaryDirectory(dir=output_dir / "raw") as temporary:
        decoded = Path(temporary) / "decoded.pcm"
        for row in sources:
            source = ROOT / row["path"]
            source_hash = original_hashes[row["clip_id"]]
            decode_pcm(source, decoded)
            samples = decoded.stat().st_size // 2
            if samples < SAMPLES:
                raise ValueError(f"{row['clip_id']}: at least 3.0 seconds of audio is required.")
            background = row["label"] == "background"
            exclusions = []
            accepted = 0
            if background:
                windows = ((index, index * SAMPLES, SAMPLES)
                           for index in range(samples // SAMPLES))
            else:
                values = np.fromfile(decoded, dtype="<i2")
                offset = loudest_start(values)
                del values
                windows = iter([(0, offset, SAMPLES)])
            with decoded.open("rb") as pcm_source:
                for index, offset, length in windows:
                    pcm_source.seek(offset * 2)
                    pcm = pcm_source.read(length * 2)
                    if not np.any(np.frombuffer(pcm, dtype="<i2")):
                        exclusions.append({"offset_samples": offset, "duration_seconds": 3.0, "reason": "wholly_silent"})
                        continue
                    clip_id = f"{row['clip_id']}__{index:06d}"
                    target = destination_dir / f"{clip_id}.wav"
                    reusable = False
                    try:
                        reusable = validate_wav(target) == pcm
                    except (OSError, ValueError):
                        pass
                    if not reusable:
                        write_pcm_wav(target, pcm)
                    recorded_at = (timestamp(row["recorded_at"]) + timedelta(seconds=offset / RATE)).isoformat().replace("+00:00", "Z")
                    manifest.append(row | {"clip_id": clip_id, "path": portable_path(target), "recorded_at": recorded_at})
                    clips.append({"clip_id": clip_id, "parent_clip_id": row["clip_id"],
                                  "group_id": source_hash, "source_sha256": source_hash,
                                  "offset_samples": offset, "offset_seconds": offset / RATE,
                                  "duration_seconds": 3.0, "audio_sha256": sha256_file(target),
                                  "preprocessing": BACKGROUND_VERSION if background else PREPROCESS_VERSION})
                    accepted += 1
            if sha256_file(source) != source_hash:
                raise ValueError(f"{row['clip_id']}: source changed during conversion; rerun.")
            source_reports.append({"parent_clip_id": row["clip_id"], "source_sha256": source_hash,
                "label": row["label"], "decoded_seconds": samples / RATE,
                "accepted_windows": accepted, "accepted_seconds": accepted * 3,
                "silent_windows": len(exclusions), "excluded_windows": exclusions,
                "trailing_seconds": (samples % SAMPLES) / RATE if background else 0.0,
                "uncropped_seconds": (samples - SAMPLES) / RATE if not background else 0.0})
    if not manifest:
        raise ValueError("No non-silent three-second clips remain; existing outputs were preserved.")
    manifest.sort(key=lambda row: row["clip_id"])
    clips.sort(key=lambda row: row["clip_id"])
    encoded = manifest_bytes(manifest)
    digest = hashlib.sha256(encoded).hexdigest()
    metadata = {"version": 1, "generation": generation, "manifest_sha256": digest, "clips": clips}
    quality = {"status": "prepared", "manifest_sha256": digest, "rows": len(manifest),
               "labels": dict(Counter(row["label"] for row in manifest)), "sources": source_reports,
               "accepted_seconds": len(manifest) * 3,
               "background_accepted_seconds": sum(r["accepted_seconds"] for r in source_reports if r["label"] == "background"),
               "silent_excluded_seconds": sum(r["silent_windows"] * 3 for r in source_reports),
               "trailing_seconds": sum(r["trailing_seconds"] for r in source_reports)}
    takes = Counter(row["label"] for row in sources if row["label"] != "background")
    quality["target_deficits"] = {label: max(0, 20 - takes[label])
        for label in sorted(LABELS - {"background"})}
    quality["target_deficits"]["background_seconds"] = max(0, 3600 - quality["background_accepted_seconds"])
    quality["collection_target_met"] = not any(quality["target_deficits"].values())
    # Publish the manifest last; its hash binds both companion files to this generation.
    write_json(output_dir / "manifests/recordings_metadata.json", metadata)
    write_json(output_dir / "reports/recordings_quality.json", quality)
    atomic_bytes(output_dir / "manifests/recordings.csv", encoded)
    print(f"Prepared {len(manifest)} recording clips; background_seconds={quality['background_accepted_seconds']}.")
    return manifest


def read_prepared(manifest: Path) -> tuple[list[dict[str, str]], list[Path]]:
    rows = read_csv(manifest)
    metadata_path = manifest.with_name("recordings_metadata.json")
    quality_path = manifest.parent.parent / "reports/recordings_quality.json"
    metadata = json.loads(metadata_path.read_text())
    quality = json.loads(quality_path.read_text())
    digest = sha256_file(manifest)
    identifiers = [row["clip_id"] for row in rows]
    if (metadata.get("manifest_sha256") != digest or quality.get("manifest_sha256") != digest
            or quality.get("rows") != len(rows) or len(set(identifiers)) != len(rows)
            or identifiers != sorted(identifiers)):
        raise ValueError("Recording manifest or quality metadata is stale; rerun preparation.")
    clips = metadata.get("clips", [])
    if [clip.get("clip_id") for clip in clips] != identifiers:
        raise ValueError("Recording provenance is not aligned with the manifest.")
    for row, clip in zip(rows, clips, strict=True):
        timestamp(row["recorded_at"])
        if (row["label"] not in LABELS or row["source"] != "ours" or row["fold"]
                or not row["device"].strip() or clip.get("duration_seconds") != 3.0
                or clip.get("group_id") != clip.get("source_sha256")):
            raise ValueError("Invalid prepared recording metadata.")
        path = ROOT / row["path"]
        if path.is_file() and sha256_file(path) != clip.get("audio_sha256"):
            raise ValueError("Prepared recording changed; rerun preparation before embedding.")
    return rows, [metadata_path, quality_path]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output-dir", type=Path, default=DATA)
    parser.add_argument("--raw-dir", type=Path, help="Allowed private source directory; defaults to output-dir/raw.")
    args = parser.parse_args()
    try:
        prepare(args.input, args.output_dir, args.raw_dir)
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        parser.exit(1, f"Recording preparation stopped: {exc}\n")


if __name__ == "__main__":
    main()
