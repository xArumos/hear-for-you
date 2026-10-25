"""False positives and misses for the /detect unknown gate and the full pipeline, on held-out ESC-50 clips.

Negatives are routine household sounds that should never alert. Positives are sounds that may need
attention, alone and mixed with typing or footsteps. For each clip this records:
- relevant: the describe model's relevance flag (gemini.describe_relevance), the gate on unknown alerts;
- smoke / builtin: whether the smoke-alarm rule or the built-in classifier fires on it;
- alerts: what /detect would do with no taught sounds, assuming the clip is loud (smoke, builtin or relevant).

Unlike the other eval scripts this one calls Gemini (one describe and one embed per clip), because a relevance
judgement can't be precomputed into data/embeddings/. It paces itself under the free-tier limits and resumes
from results/relevance_clips.csv, so a rerun only costs the clips not done yet. Needs api/.env and the ESC-50
archive from `uv run --project ../data python ../data/download_esc50.py`.

    uv run --project ../api python eval_relevance.py
"""

import csv
import io
import random
import subprocess
import sys
import time
import zipfile
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "api"))
sys.path.insert(0, str(ROOT / "data"))

from app import detectors, gemini, smoke_alarm  # noqa: E402
from convert import RATE, loudest_window  # noqa: E402

RESULTS = Path(__file__).resolve().parent / "results"
CLIPS_CSV = RESULTS / "relevance_clips.csv"
SUMMARY_CSV = RESULTS / "relevance_summary.csv"
MANIFEST = ROOT / "data/manifests/esc50.csv"

NEGATIVE = [
    "keyboard_typing", "mouse_click", "footsteps", "clock_tick", "breathing",
    "vacuum_cleaner", "washing_machine", "drinking_sipping", "brushing_teeth",
]
POSITIVE = [
    "glass_breaking", "siren", "door_wood_knock", "clock_alarm",
    "crying_baby", "dog", "car_horn", "church_bells",
]
MIX_BACKGROUNDS = ["keyboard_typing", "footsteps"]
PER_CLASS = 5
SEED = 42
DESCRIBE_INTERVAL_S = 4.5  # describe model free tier: 15 requests per minute
FIELDS = ["clip_id", "group", "category", "relevant", "smoke", "builtin", "alerts", "description"]


def decode(content: bytes) -> np.ndarray:
    """ESC-50 WAV bytes -> the loudest 3 s window at 16 kHz mono int16, as data/convert.py does it."""
    result = subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-i", "pipe:0", "-ac", "1", "-ar", str(RATE),
         "-c:a", "pcm_s16le", "-f", "s16le", "pipe:1"],
        input=content, capture_output=True, check=True, timeout=60,
    )
    return loudest_window(np.frombuffer(result.stdout, dtype="<i2"))


def mix(target: np.ndarray, background: np.ndarray) -> np.ndarray:
    """Target and background at equal RMS, scaled so the mix doesn't clip."""
    t, b = target.astype(np.float64), background.astype(np.float64)
    b *= np.sqrt(np.mean(t**2) / max(np.mean(b**2), 1.0))
    mixed = t + b
    return (mixed * min(1.0, 32_000 / max(np.abs(mixed).max(), 1.0))).astype("<i2")


def to_wav(pcm: np.ndarray) -> bytes:
    buf = io.BytesIO()
    sf.write(buf, pcm, RATE, format="WAV", subtype="PCM_16")
    return buf.getvalue()


def choose(rows: list[dict[str, str]], used: set[str]) -> dict[str, list[str]]:
    """PER_CLASS clips per category the built-in classifier never trained on.

    Clips outside data/manifests/esc50.csv where possible. The five built-in categories are all in the manifest,
    so those come from fold 5, the classifier's held-out test fold.
    """
    rng = random.Random(SEED)
    chosen: dict[str, list[str]] = {}
    for category in NEGATIVE + POSITIVE:
        names = sorted(r["filename"] for r in rows if r["category"] == category and r["filename"] not in used)
        if len(names) < PER_CLASS:
            names = sorted(r["filename"] for r in rows if r["category"] == category and r["fold"] == "5")
        chosen[category] = rng.sample(names, PER_CLASS)
    return chosen


def clips(archive: zipfile.ZipFile, prefix: str) -> list[tuple[str, str, str, np.ndarray]]:
    """(clip_id, group, category, pcm) for every negative, positive and mixed clip."""
    with archive.open(prefix + "meta/esc50.csv") as handle:
        rows = list(csv.DictReader(io.TextIOWrapper(handle)))
    with MANIFEST.open(newline="") as handle:
        used = {Path(r["path"]).stem + ".wav" for r in csv.DictReader(handle)}
    chosen = choose(rows, used)
    pcm = {name: decode(archive.read(prefix + "audio/" + name)) for names in chosen.values() for name in names}
    out = [(Path(n).stem, "negative", c, pcm[n]) for c in NEGATIVE for n in chosen[c]]
    out += [(Path(n).stem, "positive", c, pcm[n]) for c in POSITIVE for n in chosen[c]]
    for i, category in enumerate(POSITIVE):
        for j, background in enumerate(MIX_BACKGROUNDS):
            target, under = chosen[category][j], chosen[background][i % PER_CLASS]
            out.append((f"{Path(target).stem}+{Path(under).stem}", "mixed", category, mix(pcm[target], pcm[under])))
    return out


def judge(pcm: np.ndarray) -> dict[str, object]:
    wav = to_wav(pcm)
    described = gemini.describe_relevance(wav)
    smoke = smoke_alarm.detect(pcm.astype(np.float32) / 32768.0).detected
    builtin = detectors.match_builtin(gemini.embed_audio(wav))
    relevant = None if described is None else described.relevant
    return {
        "relevant": "failed" if relevant is None else relevant,
        "smoke": smoke,
        "builtin": builtin[0] if builtin else "",
        "alerts": bool(smoke or builtin or relevant),
        "description": "" if described is None else described.description,
    }


def summarize(rows: list[dict[str, str]]) -> list[tuple[str, float]]:
    def rate(group: str, column: str, positive: bool) -> tuple[float, float]:
        picked = [r for r in rows if r["group"] == group]
        hits = sum((r[column] == "True") == positive for r in picked)
        return hits, len(picked)

    metrics: list[tuple[str, float]] = []
    for column, name in [("relevant", "relevance"), ("alerts", "pipeline")]:
        fp, n_neg = rate("negative", column, True)
        metrics += [(f"{name}_false_positive_rate", fp / n_neg), (f"{name}_false_positives", fp)]
        for group in ["positive", "mixed"]:
            missed, n = rate(group, column, False)
            metrics += [(f"{name}_miss_rate_{group}", missed / n), (f"{name}_misses_{group}", missed)]
    negatives = [r for r in rows if r["group"] == "negative"]
    metrics += [
        ("negatives", len(negatives)),
        ("positives", sum(r["group"] == "positive" for r in rows)),
        ("mixed", sum(r["group"] == "mixed" for r in rows)),
        ("describe_failures", sum(r["relevant"] == "failed" for r in rows)),
        ("builtin_fired_on_negatives", sum(bool(r["builtin"]) for r in negatives)),
        ("smoke_fired_on_negatives", sum(r["smoke"] == "True" for r in negatives)),
    ]
    return metrics


def main() -> None:
    [archive_path] = sorted((ROOT / "data/raw").glob("esc50-*.zip"))
    revision = archive_path.stem.removeprefix("esc50-")
    detectors.load_builtin()
    done: dict[str, dict[str, str]] = {}
    if CLIPS_CSV.is_file():
        with CLIPS_CSV.open(newline="") as handle:
            done = {r["clip_id"]: r for r in csv.DictReader(handle) if r["relevant"] != "failed"}
    with zipfile.ZipFile(archive_path) as archive:
        todo = clips(archive, f"ESC-50-{revision}/")
    RESULTS.mkdir(exist_ok=True)
    rows: list[dict[str, str]] = []
    for clip_id, group, category, pcm in todo:
        if clip_id in done:
            rows.append(done[clip_id])
            continue
        start = time.monotonic()
        row = {"clip_id": clip_id, "group": group, "category": category, **judge(pcm)}
        rows.append({k: str(v) for k, v in row.items()})
        print(f"{len(rows):3}/{len(todo)} {group:8} {category:16} relevant={row['relevant']!s:6} "
              f"alerts={row['alerts']!s:5} {row['description']}", flush=True)
        with CLIPS_CSV.open("w", newline="") as handle:  # rewrite each time, so a crash keeps progress
            writer = csv.DictWriter(handle, FIELDS)
            writer.writeheader()
            writer.writerows(rows + [r for r in done.values() if r["clip_id"] not in {x["clip_id"] for x in rows}])
        time.sleep(max(0.0, DESCRIBE_INTERVAL_S - (time.monotonic() - start)))

    metrics = summarize(rows)
    with SUMMARY_CSV.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["metric", "value"])
        writer.writerows((name, round(value, 3)) for name, value in metrics)
    for name, value in metrics:
        print(f"{name:36} {value:.3f}")


if __name__ == "__main__":
    main()
