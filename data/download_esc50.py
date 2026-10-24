"""Download pinned ESC-50, select 260 clips, convert, and write a manifest."""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import random
import shutil
import urllib.request
import wave
import zipfile

from convert import PREPROCESS_VERSION, convert_audio, validate_wav

from dataset_io import DATA, ROOT, FIELDS, atomic_bytes

REVISION = "33c8ce9eb2cf0b1c2f8bcf322eb349b6be34dbb6"
URL = f"https://codeload.github.com/karolpiczak/ESC-50/zip/{REVISION}"
BUILTINS = {
    "dog": "builtin_dog_bark", "crying_baby": "builtin_crying_baby",
    "door_wood_knock": "builtin_door_knock", "glass_breaking": "builtin_glass_breaking",
    "siren": "builtin_siren",
}


def read_metadata(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    counts = Counter(row["category"] for row in rows)
    if len(rows) != 2000 or len(counts) != 50 or set(counts.values()) != {40}:
        raise ValueError("ESC-50 metadata must contain 50 classes with 40 clips each.")
    if len({r["filename"] for r in rows}) != 2000:
        raise ValueError("Duplicate ESC-50 filename.")
    folds = Counter((r["category"], r["fold"]) for r in rows)
    if len(folds) != 250 or set(folds.values()) != {8}:
        raise ValueError("Expected eight clips per category per original fold.")
    for row in rows:
        name = row["filename"]
        if Path(name).name != name or not name.endswith(".wav") or row["fold"] not in {"1", "2", "3", "4", "5"}:
            raise ValueError("Invalid ESC-50 filename or fold.")
    return rows


def select_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    rng = random.Random(42)
    selected = [r for r in rows if r["category"] in BUILTINS]
    categories = sorted({r["category"] for r in rows} - set(BUILTINS) - {"clock_alarm"})
    if len(categories) != 44:
        raise ValueError("Expected 44 eligible other categories.")
    used: Counter[str] = Counter()
    for fold in range(1, 6):
        available = categories.copy()
        for _ in range(12):
            minimum = min(used[c] for c in available)
            category = rng.choice([c for c in available if used[c] == minimum])
            candidates = sorted((r for r in rows if r["category"] == category
                                 and int(r["fold"]) == fold), key=lambda r: r["filename"])
            selected.append(rng.choice(candidates))
            used[category] += 1
            available.remove(category)
    return sorted(selected, key=lambda r: (int(r["fold"]),
                  BUILTINS.get(r["category"], "other"), Path(r["filename"]).stem))


def validate_archive(archive: zipfile.ZipFile) -> None:
    prefix = f"ESC-50-{REVISION}"
    for entry in archive.infolist():
        path = PurePosixPath(entry.filename)
        mode = entry.external_attr >> 16
        if (path.is_absolute() or ".." in path.parts or not path.parts
                or path.parts[0] != prefix or "\\" in entry.filename
                or (mode & 0o170000) == 0o120000):
            raise ValueError("Unsafe archive entry.")
    bad = archive.testzip()
    if bad:
        raise ValueError("ESC-50 archive failed CRC validation.")


def download(raw: Path) -> Path:
    raw.mkdir(parents=True, exist_ok=True)
    archive_path = raw / f"esc50-{REVISION}.zip"
    if not archive_path.exists():
        temporary = archive_path.with_suffix(".zip.part")
        try:
            print("Downloading official ESC-50 archive...", flush=True)
            with urllib.request.urlopen(URL, timeout=60) as source, temporary.open("wb") as output:
                shutil.copyfileobj(source, output)
            with zipfile.ZipFile(temporary) as archive:
                validate_archive(archive)
            os.replace(temporary, archive_path)
        finally:
            temporary.unlink(missing_ok=True)
    with zipfile.ZipFile(archive_path) as archive:
        validate_archive(archive)
        # Extract only the metadata and audio used here, never arbitrary archive files.
        prefix = f"ESC-50-{REVISION}/"
        metadata = raw / "esc50" / "meta" / "esc50.csv"
        atomic_bytes(metadata, archive.read(prefix + "meta/esc50.csv"))
        rows = read_metadata(metadata)
        for row in select_rows(rows):
            target = raw / "esc50" / "audio" / row["filename"]
            member = archive.getinfo(prefix + "audio/" + row["filename"])
            # Compare bytes to the pinned archive before reusing a local original.
            content = archive.read(member)
            if not target.exists() or hashlib.sha256(target.read_bytes()).digest() != hashlib.sha256(content).digest():
                atomic_bytes(target, content)
            with wave.open(str(target), "rb") as audio:
                if (audio.getnchannels(), audio.getsampwidth(), audio.getframerate(),
                        audio.getnframes()) != (1, 2, 44100, 220500):
                    raise ValueError(f"Unexpected upstream WAV: {target.name}")
    return metadata


def prepare(metadata: Path, smoke_only: bool = False) -> list[dict[str, str]]:
    selected = select_rows(read_metadata(metadata))
    smoke_ids = {next(r["filename"] for r in selected
                      if BUILTINS.get(r["category"]) == label and int(r["fold"]) < 5)
                 for label in BUILTINS.values()}
    manifest = []
    for row in selected:
        source = DATA / "raw/esc50/audio" / row["filename"]
        destination = DATA / "raw/converted" / row["filename"]
        if not smoke_only or row["filename"] in smoke_ids:
            fingerprint = hashlib.sha256(source.read_bytes() + PREPROCESS_VERSION.encode()).hexdigest()
            marker = destination.with_suffix(".json")
            reusable = False
            try:
                reusable = json.loads(marker.read_text()) == {
                    "fingerprint": fingerprint,
                    "output_sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
                }
                validate_wav(destination)
            except (OSError, ValueError):
                reusable = False
            if not reusable:
                convert_audio(source, destination)
                atomic_bytes(marker, json.dumps({"fingerprint": fingerprint,
                    "output_sha256": hashlib.sha256(destination.read_bytes()).hexdigest()}).encode())
        manifest.append(dict(zip(FIELDS, [Path(row["filename"]).stem,
            destination.relative_to(ROOT).as_posix(), BUILTINS.get(row["category"], "other"),
            "esc50", row["fold"], "", ""], strict=True)))
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(manifest)
    atomic_bytes(DATA / "manifests/esc50.csv", output.getvalue().encode())
    print(f"Manifest: {len(manifest)} rows; converted {'5' if smoke_only else len(manifest)} clips.")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke-test", action="store_true", help="Convert only five training clips.")
    args = parser.parse_args()
    try:
        prepare(download(DATA / "raw"), args.smoke_test)
    except Exception as exc:
        parser.exit(1, f"Dataset preparation failed: {exc}\n")


if __name__ == "__main__":
    main()
