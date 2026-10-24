"""Combine eval/results/*.csv into api/metrics.json, in exactly the GET /api/metrics shape in CONTRACT.md.

A number is only filled in when the script that measures it has written its results file. Anything not
measured yet is null, so the Model Card page never shows a placeholder as if it were real.

    uv run --project ../api python write_metrics.py
"""

import csv
import json
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = Path(__file__).resolve().parent / "results"
OUTPUT = ROOT / "api/metrics.json"


def read_summary(name: str) -> dict[str, str] | None:
    """metric -> value from results/<name>.csv, or None if that script hasn't run yet."""
    path = RESULTS / f"{name}.csv"
    if not path.is_file():
        return None
    with path.open(newline="") as handle:
        return {row["metric"]: row["value"] for row in csv.DictReader(handle)}


def number(summary: dict[str, str] | None, metric: str, digits: int = 3) -> float | None:
    if summary is None or metric not in summary:
        return None
    return round(float(summary[metric]), digits)


def integer(summary: dict[str, str] | None, metric: str) -> int | None:
    value = number(summary, metric, 0)
    return None if value is None else int(value)


def build() -> dict[str, object]:
    builtin = read_summary("builtin_summary")  # train_builtin.py
    zero_shot = read_summary("zero_shot_summary")  # zero_shot.py (not written yet)
    few_shot = read_summary("few_shot_summary")  # few_shot.py (not written yet)
    false_alarms = read_summary("false_alarms_summary")  # false_alarms.py (not written yet)
    latency = read_summary("latency_summary")  # latency.py (not written yet)
    return {
        "builtin_accuracy": {
            "zero_shot": number(zero_shot, "accuracy"),
            # The p > 0.6 rule /detect uses, not plain argmax: the number users actually get.
            "trained": number(builtin, "accuracy_with_gate"),
            "test_fold": integer(builtin, "test_fold") or 5,
        },
        "taught_miss_rate": number(few_shot, "miss_rate"),
        "false_alarms_per_hour": number(false_alarms, "false_alarms_per_hour", 2),
        "latency_ms_median": integer(latency, "latency_ms_median"),
        "gemini_calls_per_hour": {
            "gate_off": integer(false_alarms, "gemini_calls_per_hour_gate_off"),
            "gate_on": integer(false_alarms, "gemini_calls_per_hour_gate_on"),
        },
        "updated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def main() -> None:
    metrics = build()
    OUTPUT.write_text(json.dumps(metrics, indent=2) + "\n")
    print(json.dumps(metrics, indent=2))
    print(f"wrote {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
