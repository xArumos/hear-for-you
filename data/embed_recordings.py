"""Embed prepared local recordings with the same smoke gate as ESC-50."""
from __future__ import annotations

import argparse
from pathlib import Path

from dataset_io import DATA
from embedding_core import CACHE, run_dataset
from prepare_recordings import read_prepared


def smoke_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    selected = []
    for label in sorted({row["label"] for row in rows}):
        selected.append(next(row for row in rows if row["label"] == label))
    for row in rows:
        if len(selected) >= 5:
            break
        if row not in selected:
            selected.append(row)
    return selected


def run(manifest: Path, smoke: bool, dry_run: bool) -> None:
    rows, companions = read_prepared(manifest)
    if len(rows) < 5:
        raise ValueError("Prepare at least five clips before the recording smoke test.")
    run_dataset(rows, manifest, manifest.parent.parent, "recordings", smoke_rows(rows),
                smoke, dry_run, CACHE, companions)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DATA / "manifests/recordings.csv")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--smoke-test", action="store_true")
    mode.add_argument("--full", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        run(args.manifest, args.smoke_test, args.dry_run)
    except (OSError, ValueError, RuntimeError) as exc:
        parser.exit(1, f"Recording embedding stopped: {exc}\n")


if __name__ == "__main__":
    main()
