"""Serves api/metrics.json, which eval/write_metrics.py writes. Read per request so new numbers show up
without restarting the server."""

import json
from pathlib import Path

from app.errors import NotFound

METRICS_PATH = Path(__file__).resolve().parent.parent / "metrics.json"


def read_metrics(path: Path | None = None) -> dict[str, object]:
    path = path or METRICS_PATH
    if not path.is_file():
        raise NotFound("No metrics yet. Run eval/write_metrics.py.")
    metrics = json.loads(path.read_text())
    if not isinstance(metrics, dict):
        raise ValueError(f"{path.name} must hold a JSON object.")
    return metrics
