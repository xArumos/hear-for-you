import csv
import json
import runpy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import metrics
from tests.test_routes import assert_error_shape

ROOT = Path(__file__).resolve().parents[2]
CONTRACT_KEYS = {
    "builtin_accuracy", "taught_miss_rate", "false_alarms_per_hour",
    "latency_ms_median", "gemini_calls_per_hour", "updated_at",
}


def check_shape(body: dict[str, object]) -> None:
    """The /api/metrics shape in CONTRACT.md; unmeasured numbers are null."""
    assert set(body) == CONTRACT_KEYS
    builtin = body["builtin_accuracy"]
    assert isinstance(builtin, dict) and set(builtin) == {"zero_shot", "trained", "test_fold"}
    assert builtin["test_fold"] == 5
    calls = body["gemini_calls_per_hour"]
    assert isinstance(calls, dict) and set(calls) == {"gate_off", "gate_on"}
    for value in (builtin["zero_shot"], builtin["trained"], body["taught_miss_rate"]):
        assert value is None or 0 <= value <= 1
    assert isinstance(body["updated_at"], str) and body["updated_at"].endswith("Z")


def test_get_metrics(client: TestClient) -> None:
    res = client.get("/api/metrics")
    assert res.status_code == 200
    body = res.json()
    assert isinstance(body.pop("latency_ms"), int)
    check_shape(body)
    assert body == json.loads(metrics.METRICS_PATH.read_text())


def test_missing_metrics_file(client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(metrics, "METRICS_PATH", tmp_path / "metrics.json")
    res = client.get("/api/metrics")
    assert res.status_code == 404
    assert_error_shape(res.json(), "not_found")


def test_committed_metrics_match_eval_results() -> None:
    """api/metrics.json carries the same trained accuracy eval/ measured (and the Model Card shows)."""
    body = json.loads(metrics.METRICS_PATH.read_text())
    check_shape(body)
    with (ROOT / "eval/results/builtin_summary.csv").open(newline="") as handle:
        summary = {row["metric"]: row["value"] for row in csv.DictReader(handle)}
    assert body["builtin_accuracy"]["trained"] == round(float(summary["accuracy_with_gate"]), 3)


def test_write_metrics_builds_contract_shape() -> None:
    script = runpy.run_path(str(ROOT / "eval/write_metrics.py"))
    check_shape(script["build"]())
