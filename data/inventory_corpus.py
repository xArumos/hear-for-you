"""Inventory local original audio without treating unreviewed files as evidence."""
from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from dataset_io import DATA, portable_path, sha256_file, write_json


def inventory(raw: Path) -> dict[str, object]:
    raw = raw.resolve()
    audio = []
    for path in sorted(raw.rglob("*")):
        if path.suffix.lower() not in {".wav", ".mp3", ".m4a", ".aiff", ".aif", ".flac", ".ogg", ".webm"} or not path.is_file():
            continue
        relative = path.relative_to(raw)
        if relative.parts[0] in {"prepared", "converted", "recordings", "smoke", "embedding-cache"}:
            continue
        if not path.resolve().is_relative_to(raw):
            continue
        audio.append({"path": portable_path(path), "sha256": sha256_file(path),
                      "bytes": path.stat().st_size,
                      "collection": "esc50" if relative.parts[0] == "esc50" else "unreviewed",
                      "eligible_for_corpus": False})
    return {"version": 1, "counts": dict(Counter(a["collection"] for a in audio)), "files": audio,
            "note": "Inventory is not consent, license verification, collection completion or accuracy evidence."}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=DATA / "raw")
    args = parser.parse_args()
    result = inventory(args.raw_dir)
    destination = args.raw_dir / "status/corpus_inventory.json"
    write_json(destination, result)
    print(f"Original audio counts: {result['counts']}; private inventory: {destination}")


if __name__ == "__main__":
    main()
