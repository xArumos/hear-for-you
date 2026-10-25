"""Is a door-knock-specific acceptance cutoff (below the global 0.6) justified? Issue #27, item 3.

The built-in classifier ranks door knocks first almost always, but some fall under the global p > 0.6 gate.
This script measures, for knock cutoffs from 0.30 to 0.60, how many knocks would be accepted and how many
non-knock clips would become false knocks. Never by looking at the reported fold.

- dev (chooses the cutoff): ESC-50 folds 1-4.
  - Knocks and other labelled clips in data/embeddings/, each scored by a model trained the same way
    (train_builtin.py's recipe) on the other three training folds, so no clip is scored by a model that saw it.
  - Knock-like household sounds from ESC-50 folds 1-4 that the classifier never trained on: typing, mouse clicks,
    footsteps, clapping, laughing, coughing. Scored by the shipped model, as in /detect.
  - Each dev knock mixed under a dev household clip at 0 dB and -6 dB (knock quieter): a rough stand-in for a knock
    further away in a noisy room. Not a real distance test.
- test (reported, never used to choose): the same groups from fold 5, all scored by the shipped model.

Choice rule: the lowest cutoff whose dev false knocks equal the false knocks at 0.6 and whose dev knock
acceptance is higher. If none qualifies, keep 0.6.

It also compares retraining instead of a cutoff (results/knock_retrain.csv): train_builtin.py's recipe plus the
dev household clips as "other", and optionally the dev noisy knocks as knock. Variants are compared by
leave-one-fold-out over folds 1-4; fold 5 is shown for reference only. This doesn't change the shipped model.

Calls the Gemini embedding model for the household and mixed clips (the eval/AGENTS.md exception), caching
vectors in data/raw/eval-cache/ (gitignored) so a rerun costs nothing. Needs api/.env and the ESC-50 archive.

    uv run --project ../api python eval_knock.py
"""

import csv
import io
import sys
import time
import zipfile
from pathlib import Path

import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.model_selection import PredefinedSplit

from eval_relevance import RESULTS, ROOT, decode, to_wav  # also puts api/ and data/ on sys.path
from train_builtin import load, make_model

from app import detectors, gemini  # noqa: E402

KNOCK = "builtin_door_knock"
OTHER = "other"
CHOSEN_C = 0.001  # train_builtin.py's leave-one-fold-out choice (eval/results/builtin_summary.csv)
CONFUSERS = ["keyboard_typing", "mouse_click", "footsteps", "clapping", "laughing", "coughing"]
MIX_SNR_DB = [0.0, -6.0]
CUTOFFS = [round(0.30 + 0.05 * i, 2) for i in range(7)]  # 0.30 ... 0.60
GLOBAL = 0.6
CACHE = ROOT / "data/raw/eval-cache/knock_embeddings.npz"
EMBED_INTERVAL_S = 0.7  # embedding free tier: 100 requests per minute


def mix_at(knock: np.ndarray, background: np.ndarray, snr_db: float) -> np.ndarray:
    """Knock over background at snr_db (knock RMS relative to background RMS), scaled so it doesn't clip."""
    k, b = knock.astype(np.float64), background.astype(np.float64)
    b *= np.sqrt(np.mean(k**2) / max(np.mean(b**2), 1.0)) * 10 ** (-snr_db / 20)
    mixed = k + b
    return (mixed * min(1.0, 32_000 / max(np.abs(mixed).max(), 1.0))).astype("<i2")


class Embeddings:
    """Gemini embeddings by clip id, cached on disk so reruns don't spend quota."""

    def __init__(self) -> None:
        self.vectors: dict[str, np.ndarray] = {}
        if CACHE.is_file():
            with np.load(CACHE) as data:
                self.vectors = {key: data[key] for key in data.files}

    def get(self, clip_id: str, pcm: np.ndarray) -> np.ndarray:
        if clip_id not in self.vectors:
            start = time.monotonic()
            self.vectors[clip_id] = gemini.embed_audio(to_wav(pcm))
            CACHE.parent.mkdir(parents=True, exist_ok=True)
            np.savez(CACHE, **self.vectors)
            time.sleep(max(0.0, EMBED_INTERVAL_S - (time.monotonic() - start)))
        return self.vectors[clip_id]


def fold_models(X: np.ndarray, y: np.ndarray, folds: np.ndarray) -> dict[int, CalibratedClassifierCV]:
    """For each training fold f, train_builtin.py's recipe on the other three training folds."""
    models = {}
    for f in (1, 2, 3, 4):
        keep = (folds != 5) & (folds != f)
        split = PredefinedSplit(np.unique(folds[keep], return_inverse=True)[1])
        model = CalibratedClassifierCV(make_model(CHOSEN_C), method="sigmoid", cv=split)
        models[f] = model.fit(X[keep], y[keep])
    return models


def ranking(model: object, classes: list[str], vec: np.ndarray) -> list[tuple[str, float]]:
    proba = model.predict_proba(vec.reshape(1, -1))[0]  # type: ignore[attr-defined]
    return sorted(zip(classes, map(float, proba)), key=lambda pair: -pair[1])


def accepted_knock(rank: list[tuple[str, float]], cutoff: float) -> bool:
    """The /detect rule with a knock-specific cutoff: knock is the top class and above it."""
    label, p = rank[0]
    return label == KNOCK and p > cutoff


RETRAIN_VARIANTS = {"shipped recipe": set(), "+household": {"household"}, "+household+noisy": {"household", "mixed"}}


def compare_retraining(clips: list[dict[str, object]], X: np.ndarray, y: np.ndarray, folds: np.ndarray,
                       vectors: dict[str, np.ndarray]) -> list[list[object]]:
    """Rows of (variant, split, group, correct, n) for the retraining alternative to a knock cutoff."""
    extra = [  # (vector, label, fold, kind, group); ESC-50 clip ids start with their fold number
        (vectors[str(c["clip_id"])], KNOCK if str(c["group"]).startswith("mixed") else OTHER,
         int(str(c["clip_id"])[0]), "mixed" if str(c["group"]).startswith("mixed") else "household", str(c["group"]))
        for c in clips if str(c["group"]).startswith(("household", "mixed"))
    ]

    def fit(train_folds: set[int], kinds: set[str]) -> CalibratedClassifierCV:
        keep = np.isin(folds, list(train_folds))
        ex = [e for e in extra if e[2] in train_folds and e[3] in kinds]
        Xt = np.vstack([X[keep]] + ([np.stack([e[0] for e in ex])] if ex else []))
        yt = np.concatenate([y[keep], np.asarray([e[1] for e in ex], dtype=y.dtype)])
        ft = np.concatenate([folds[keep], np.asarray([e[2] for e in ex], dtype=int)])
        split = PredefinedSplit(np.unique(ft, return_inverse=True)[1])
        return CalibratedClassifierCV(make_model(CHOSEN_C), method="sigmoid", cv=split).fit(Xt, yt)

    def decide(model: CalibratedClassifierCV, vec: np.ndarray) -> str:
        label, p = ranking(model, [str(c) for c in model.classes_], vec)[0]
        return label if label != OTHER and p > GLOBAL else OTHER

    def score(model: CalibratedClassifierCV, fold_set: set[int], into: dict[str, list[bool]]) -> None:
        for i in np.where(np.isin(folds, list(fold_set)))[0]:
            into.setdefault(f"esc50:{y[i]}", []).append(decide(model, X[i]) == y[i])
        for vec, label, fold, _, group in extra:
            if fold in fold_set:
                into.setdefault(group, []).append(decide(model, vec) == label)

    out: list[list[object]] = []
    for name, kinds in RETRAIN_VARIANTS.items():
        dev: dict[str, list[bool]] = {}
        for f in (1, 2, 3, 4):
            score(fit({1, 2, 3, 4} - {f}, kinds), {f}, dev)
        test: dict[str, list[bool]] = {}
        score(fit({1, 2, 3, 4}, kinds), {5}, test)
        for split, table in (("dev", dev), ("test", test)):
            for group, results in sorted(table.items()):
                out.append([name, split, group, sum(results), len(results)])
    return out


def main() -> None:
    detectors.load_builtin()
    shipped = detectors._builtin
    assert shipped is not None, "api/models/builtin_clf.joblib is missing"
    rows, X, y, folds = load()
    models = fold_models(X, y, folds)

    clips: list[dict[str, object]] = []  # split, group, clip_id, rank

    def add(split: str, group: str, clip_id: str, rank: list[tuple[str, float]], truth: str) -> None:
        clips.append({"split": split, "group": group, "clip_id": clip_id, "truth": truth, "rank": rank})

    for i, row in enumerate(rows):
        fold = int(row["fold"])
        model, classes = (shipped.classifier, shipped.classes) if fold == 5 else (models[fold], shipped.classes)
        if fold != 5:
            assert [str(c) for c in models[fold].classes_] == shipped.classes
        group = "esc50_knock" if y[i] == KNOCK else "esc50_not_knock"
        add("test" if fold == 5 else "dev", group, row["clip_id"], ranking(model, classes, X[i]), str(y[i]))

    embeddings = Embeddings()
    [archive_path] = sorted((ROOT / "data/raw").glob("esc50-*.zip"))
    prefix = f"ESC-50-{archive_path.stem.removeprefix('esc50-')}/"
    used = {row["clip_id"] + ".wav" for row in rows}
    with zipfile.ZipFile(archive_path) as archive:
        with archive.open(prefix + "meta/esc50.csv") as handle:
            meta = list(csv.DictReader(io.TextIOWrapper(handle)))
        household = {"dev": [], "test": []}
        for m in sorted(meta, key=lambda m: m["filename"]):
            if m["category"] in CONFUSERS and m["filename"] not in used:
                household["test" if m["fold"] == "5" else "dev"].append(m)
        pcm: dict[str, np.ndarray] = {}
        for split, items in household.items():
            for m in items:
                clip_id = Path(m["filename"]).stem
                pcm[clip_id] = decode(archive.read(prefix + "audio/" + m["filename"]))
                vec = embeddings.get(clip_id, pcm[clip_id])
                add(split, f"household:{m['category']}", clip_id, ranking(shipped.classifier, shipped.classes, vec),
                    m["category"])
        for i, row in enumerate(rows):
            if y[i] != KNOCK:
                continue
            split = "test" if row["fold"] == "5" else "dev"
            knock = decode(archive.read(prefix + "audio/" + row["clip_id"] + ".wav"))
            backgrounds = household[split]
            for j, snr in enumerate(MIX_SNR_DB):
                under = backgrounds[(i * len(MIX_SNR_DB) + j) % len(backgrounds)]
                under_id = Path(under["filename"]).stem
                clip_id = f"{row['clip_id']}+{under_id}@{snr:+.0f}dB"
                vec = embeddings.get(clip_id, mix_at(knock, pcm[under_id], snr))
                model = shipped.classifier if split == "test" else models[int(row["fold"])]
                add(split, f"mixed_knock@{snr:+.0f}dB", clip_id, ranking(model, shipped.classes, vec), KNOCK)
            print(f"knock {row['clip_id']} mixed", flush=True)

    is_knock = lambda c: c["truth"] == KNOCK  # noqa: E731

    def counts(split: str, cutoff: float) -> dict[str, int]:
        picked = [c for c in clips if c["split"] == split]
        out: dict[str, int] = {}
        for group in sorted({str(c["group"]) for c in picked}):
            members = [c for c in picked if c["group"] == group]
            hits = sum(accepted_knock(c["rank"], cutoff) for c in members)  # type: ignore[arg-type]
            out[f"{group}_n"] = len(members)
            out[f"{group}_{'accepted' if is_knock(members[0]) else 'false_knocks'}"] = hits
        out["knocks_accepted"] = sum(v for k, v in out.items() if k.endswith("_accepted"))
        out["knocks_n"] = sum(1 for c in picked if is_knock(c))
        out["false_knocks"] = sum(v for k, v in out.items() if k.endswith("_false_knocks"))
        out["not_knock_n"] = sum(1 for c in picked if not is_knock(c))
        return out

    dev = {cutoff: counts("dev", cutoff) for cutoff in CUTOFFS}
    test = {cutoff: counts("test", cutoff) for cutoff in CUTOFFS}
    baseline = dev[GLOBAL]
    better = [
        cutoff for cutoff in CUTOFFS
        if cutoff < GLOBAL
        and dev[cutoff]["false_knocks"] == baseline["false_knocks"]
        and dev[cutoff]["knocks_accepted"] > baseline["knocks_accepted"]
    ]
    chosen = min(better) if better else GLOBAL

    RESULTS.mkdir(exist_ok=True)
    with (RESULTS / "knock_clips.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["split", "group", "clip_id", "truth", "top", "top_p", "second", "second_p", "p_knock"])
        for c in clips:
            rank = c["rank"]  # type: ignore[assignment]
            p_knock = dict(rank)[KNOCK]  # type: ignore[arg-type]
            writer.writerow([c["split"], c["group"], c["clip_id"], c["truth"], rank[0][0], f"{rank[0][1]:.3f}",
                             rank[1][0], f"{rank[1][1]:.3f}", f"{p_knock:.3f}"])
    with (RESULTS / "knock_cutoffs.csv").open("w", newline="") as handle:
        keys = sorted({k for table in (dev, test) for result in table.values() for k in result})
        writer = csv.writer(handle)
        writer.writerow(["split", "cutoff", *keys])
        for split, table in (("dev", dev), ("test", test)):
            for cutoff, result in table.items():
                writer.writerow([split, cutoff, *(result.get(k, "") for k in keys)])
    with (RESULTS / "knock_summary.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["metric", "value"])
        writer.writerow(["chosen_cutoff", chosen])
        for split, table in (("dev", dev), ("test", test)):
            for cutoff in sorted({GLOBAL, chosen}):
                for key in ("knocks_accepted", "knocks_n", "false_knocks", "not_knock_n"):
                    writer.writerow([f"{split}_{cutoff}_{key}", table[cutoff][key]])

    retrain = compare_retraining(clips, X, y, folds, embeddings.vectors)
    with (RESULTS / "knock_retrain.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["variant", "split", "group", "correct", "n"])
        writer.writerows(retrain)
    print("\nretraining instead of a cutoff (correct/n; knocks = clean + noisy, household = clips ignored):")
    for name in RETRAIN_VARIANTS:
        for split in ("dev", "test"):
            mine = [r for r in retrain if r[0] == name and r[1] == split]
            def total(prefixes: tuple[str, ...]) -> str:
                hits = [r for r in mine if str(r[2]).startswith(prefixes)]
                return f"{sum(int(r[3]) for r in hits)}/{sum(int(r[4]) for r in hits)}"
            print(f"  {name:18} {split:4} knocks {total(('esc50:' + KNOCK, 'mixed'))}"
                  f"  household {total(('household',))}  footsteps {total(('household:footsteps',))}"
                  f"  glass {total(('esc50:builtin_glass_breaking',))}  dog {total(('esc50:builtin_dog_bark',))}")

    for split, table in (("dev", dev), ("test", test)):
        print(f"\n{split}: cutoff  knocks accepted  false knocks")
        for cutoff, result in table.items():
            print(f"      {cutoff:.2f}   {result['knocks_accepted']:3}/{result['knocks_n']:<3}"
                  f"         {result['false_knocks']:3}/{result['not_knock_n']}")
    print(f"\nchosen knock cutoff (from dev only): {chosen}")


if __name__ == "__main__":
    sys.exit(main())
