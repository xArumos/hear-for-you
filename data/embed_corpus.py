"""Embed a prepared corpus using shared smoke gates and publish complete bundles."""
from __future__ import annotations

import argparse
from pathlib import Path

from corpus import DATASETS, read_prepared, overlap
from dataset_io import DATA, atomic_bytes
from embedding_core import CACHE, run_dataset, verify_artifacts


def smoke_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    selected = []
    for label in sorted({r["label"] for r in rows}):
        if len(selected) == 5:
            break
        selected.append(next(r for r in rows if r["label"] == label))
    for row in rows:
        if len(selected) == 5:
            break
        if row not in selected:
            selected.append(row)
    return selected


def run(manifest: Path, dataset: str, smoke: bool, dry_run: bool,
        output_dir: Path = DATA, cache: Path = CACHE) -> None:
    rows, companions = read_prepared(manifest, dataset)
    # Build artifacts in a private generation workspace first. API failures leave
    # the last published bundle untouched, including its manifest and companions.
    staging = manifest.parent / "publication"
    run_dataset(rows, manifest, staging, dataset, smoke_rows(rows), smoke, dry_run, cache, companions)
    if smoke or dry_run:
        return
    matrix = staging / f"embeddings/{dataset}_768.npy"
    report = staging / f"reports/{dataset}_validation.json"
    verify_artifacts(rows, manifest, matrix, report, companions)
    for source, target in [(matrix, output_dir / "embeddings" / matrix.name),
                           (report, output_dir / "reports" / report.name),
                           *((p, output_dir / "manifests" / p.name) for p in companions),
                           (manifest, output_dir / "manifests" / manifest.name)]:
        atomic_bytes(target, source.read_bytes())
    print(f"Published {dataset}; overlap={overlap(manifest, dataset, output_dir)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", choices=DATASETS, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=DATA)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--smoke-test", action="store_true")
    mode.add_argument("--full", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        run(args.manifest, args.dataset, args.smoke_test, args.dry_run, args.output_dir)
    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
        parser.exit(1, f"Corpus embedding stopped: {exc}\n")


if __name__ == "__main__":
    main()
