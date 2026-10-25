"""Prepare provenance-aware corpora without replacing published artifacts."""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess

from corpus import DATASETS, prepare
from dataset_io import DATA


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", choices=DATASETS, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=DATA)
    args = parser.parse_args()
    try:
        manifest = prepare(args.input, args.dataset, args.output_dir.resolve())
        print(f"Prepared manifest: {manifest}")
        print("Audio and preparation remain ignored until a successful full embedding run.")
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as exc:
        parser.exit(1, f"Corpus preparation stopped: {exc}\n")


if __name__ == "__main__":
    main()
