"""Embed the pinned ESC-50 selection with a five-clip execution gate."""
from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from dataset_io import DATA, ROOT, FIELDS, read_csv
from download_esc50 import BUILTINS, read_metadata, select_rows
from embedding_core import CACHE, run_dataset

MANIFEST = DATA / "manifests/esc50.csv"

def read_manifest(path: Path = MANIFEST, verify_selection: bool = True) -> list[dict[str, str]]:
    rows = read_csv(path)
    counts = Counter(r["label"] for r in rows)
    expected = {label: 40 for label in BUILTINS.values()} | {"other": 60}
    if counts != expected or len({r["clip_id"] for r in rows}) != 260:
        raise ValueError("Manifest must have 40 clips per builtin and 60 unique other clips.")
    if Counter(r["fold"] for r in rows if r["label"] == "other") != {str(f): 12 for f in range(1, 6)}:
        raise ValueError("Expected 12 other clips per original fold.")
    order = [(int(row["fold"]), row["label"], row["clip_id"]) for row in rows]
    if order != sorted(order):
        raise ValueError("ESC-50 rows must be ordered by fold, label and clip ID.")
    for row in rows:
        if (row["source"] != "esc50" or row["recorded_at"] or row["device"]
                or row["fold"] not in {"1", "2", "3", "4", "5"}
                or row["path"] != f"data/raw/converted/{row['clip_id']}.wav"):
            raise ValueError("Invalid ESC-50 manifest metadata.")
    if Counter((r["label"], r["fold"]) for r in rows if r["label"] != "other") != {
            (label, str(fold)): 8 for label in BUILTINS.values() for fold in range(1, 6)}:
        raise ValueError("Expected eight examples per builtin per fold.")
    if not verify_selection:
        return rows
    upstream = select_rows(read_metadata(DATA / "raw/esc50/meta/esc50.csv"))
    for row, original in zip(rows, upstream, strict=True):
        clip_id = Path(original["filename"]).stem
        expected_row = dict(zip(FIELDS, [clip_id, f"data/raw/converted/{clip_id}.wav",
            BUILTINS.get(original["category"], "other"), "esc50", original["fold"], "", ""], strict=True))
        if row != expected_row:
            raise ValueError("Manifest differs from pinned deterministic ESC-50 selection.")
    return rows


def smoke_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [next(r for r in rows if r["label"] == label and int(r["fold"]) < 5)
            for label in sorted(BUILTINS.values())]


def run(smoke: bool, dry_run: bool) -> None:
    rows = read_manifest()
    run_dataset(rows, MANIFEST, DATA, "esc50", smoke_rows(rows), smoke, dry_run, CACHE)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--smoke-test", action="store_true")
    mode.add_argument("--full", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        run(args.smoke_test, args.dry_run)
    except (OSError, ValueError, RuntimeError) as exc:
        parser.exit(1, f"Embedding stopped: {exc}\n")


if __name__ == "__main__":
    main()
