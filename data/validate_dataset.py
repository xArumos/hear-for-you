"""Verify completed data artifacts or report exactly what remains missing."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from dataset_io import DATA, ROOT, read_csv, sha256_file, write_json
from embedding_core import MODEL, verify_artifacts
from prepare_recordings import read_prepared


def validate(dataset: str, output_dir: Path = DATA) -> dict[str, object]:
    manifest = output_dir / f"manifests/{dataset}.csv"
    matrix = output_dir / f"embeddings/{dataset}_768.npy"
    report_path = output_dir / f"reports/{dataset}_validation.json"
    status_path = output_dir / f"raw/status/{dataset}.json"
    summary: dict[str, object] = {"dataset": dataset, "status": "incomplete", "model": MODEL}
    try:
        if dataset == "recordings":
            rows, companions = read_prepared(manifest)
        else:
            from embed_esc50 import read_manifest
            upstream_available = (DATA / "raw/esc50/meta/esc50.csv").is_file()
            rows, companions = read_manifest(manifest, verify_selection=upstream_available), []
        summary.update({"rows": len(rows), "labels": dict(Counter(r["label"] for r in rows)),
                        "duration_seconds": len(rows) * 3, "manifest_sha256": sha256_file(manifest),
                        "available_audio": sum((ROOT / r["path"]).is_file() for r in rows),
                        "published_matrix": matrix.is_file()})
        report = verify_artifacts(rows, manifest, matrix, report_path, companions)
        summary.update(report)
        if dataset == "recordings":
            quality = json.loads(companions[1].read_text())
            summary["collection"] = {key: quality[key] for key in (
                "background_accepted_seconds", "silent_excluded_seconds", "trailing_seconds",
                "target_deficits", "collection_target_met")}
    except (OSError, ValueError, KeyError) as exc:
        summary["status"] = "incomplete"
        summary["reason"] = str(exc)
    write_json(status_path, summary)
    print(f"{dataset}: {summary['status']}; rows={summary.get('rows', 0)}; report={status_path}")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", choices=["esc50", "recordings", "all"], default="all")
    parser.add_argument("--output-dir", type=Path, default=DATA)
    args = parser.parse_args()
    datasets = ["esc50", "recordings"] if args.dataset == "all" else [args.dataset]
    results = [validate(dataset, args.output_dir) for dataset in datasets]
    if any(result["status"] != "complete" for result in results):
        parser.exit(1)


if __name__ == "__main__":
    main()
