"""Train the built-in classifier on ESC-50 embeddings and save it to api/models/builtin_clf.joblib.

Train on folds 1-4, test once on fold 5 (never tuned on). C is chosen by leave-one-fold-out over folds 1-4.
Probabilities are calibrated with CalibratedClassifierCV, each calibrator fit on a held-out training fold.
Run from eval/ with the api environment, so the saved model matches the scikit-learn version that loads it:

    uv run --project ../api python train_builtin.py
"""

import csv
import hashlib
from datetime import UTC, datetime
from pathlib import Path

import joblib
import numpy as np
import sklearn
from sklearn.calibration import CalibratedClassifierCV
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import PredefinedSplit, cross_val_score
from sklearn.pipeline import Pipeline, make_pipeline
from sklearn.preprocessing import StandardScaler

SEED = 42
ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "data/manifests/esc50.csv"
EMBEDDINGS = ROOT / "data/embeddings/esc50_768.npy"
MODEL_PATH = ROOT / "api/models/builtin_clf.joblib"
RESULTS = Path(__file__).resolve().parent / "results"

EMBED_MODEL = "gemini-embedding-2"
DIM = 768
C_GRID = [0.001, 0.01, 0.1, 1.0, 10.0]
# Same rule as api/app/detectors.py BUILTIN_MIN_PROB: a built-in wins only above this probability.
MIN_PROB = 0.6
OTHER = "other"


def load() -> tuple[list[dict[str, str]], np.ndarray, np.ndarray, np.ndarray]:
    with MANIFEST.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    X = np.load(EMBEDDINGS, allow_pickle=False)
    assert X.dtype == np.float32 and X.shape == (len(rows), DIM), X.shape
    y = np.asarray([row["label"] for row in rows])
    folds = np.asarray([int(row["fold"]) for row in rows])
    return rows, X, y, folds


def make_model(c: float) -> Pipeline:
    return make_pipeline(
        StandardScaler(), LogisticRegression(C=c, max_iter=5000, random_state=SEED)
    )


def choose_c(X: np.ndarray, y: np.ndarray, folds: np.ndarray) -> tuple[float, dict[float, float]]:
    """Leave-one-fold-out accuracy on the training folds; ties go to the smaller (simpler) C."""
    split = PredefinedSplit(folds - 1)
    scores = {c: float(cross_val_score(make_model(c), X, y, cv=split).mean()) for c in C_GRID}
    best = max(C_GRID, key=lambda c: (round(scores[c], 6), -c))
    return best, scores


def decide(proba: np.ndarray, classes: list[str]) -> list[str]:
    """The product rule: the top class wins if it is a built-in above MIN_PROB, else "other"."""
    decisions = []
    for row in proba:
        top = int(np.argmax(row))
        decisions.append(classes[top] if classes[top] != OTHER and row[top] > MIN_PROB else OTHER)
    return decisions


def main() -> None:
    rows, X, y, folds = load()
    train, test = folds != 5, folds == 5

    c, cv_scores = choose_c(X[train], y[train], folds[train])
    for value, score in cv_scores.items():
        print(f"C={value:<6g} folds 1-4 leave-one-fold-out accuracy={score:.3f}")
    print(f"chosen C={c:g}")

    model = CalibratedClassifierCV(
        make_model(c), method="sigmoid", cv=PredefinedSplit(folds[train] - 1)
    )
    model.fit(X[train], y[train])
    classes = [str(label) for label in model.classes_]

    proba = model.predict_proba(X[test])
    argmax = [classes[i] for i in np.argmax(proba, axis=1)]
    decided = decide(proba, classes)
    truth = y[test]
    other_mask = truth == OTHER

    summary = {
        "test_fold": 5,
        "test_clips": int(test.sum()),
        "chosen_c": c,
        "accuracy_argmax": float(np.mean(np.asarray(argmax) == truth)),
        "accuracy_with_gate": float(np.mean(np.asarray(decided) == truth)),
        "other_clips_false_alarm_rate": float(np.mean(np.asarray(decided)[other_mask] != OTHER)),
        "min_prob": MIN_PROB,
    }
    per_class = {
        label: float(np.mean(np.asarray(decided)[truth == label] == label)) for label in classes
    }

    RESULTS.mkdir(exist_ok=True)
    with (RESULTS / "builtin_fold5.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["clip_id", "label", "predicted", "probability"])
        test_rows = [row for row, keep in zip(rows, test) if keep]
        for row, pred, p in zip(test_rows, decided, proba):
            writer.writerow([row["clip_id"], row["label"], pred, f"{p.max():.3f}"])
    with (RESULTS / "builtin_summary.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["metric", "value"])
        for key, value in summary.items():
            writer.writerow([key, value])
        for label, recall in per_class.items():
            writer.writerow([f"recall_{label}", recall])

    MODEL_PATH.parent.mkdir(exist_ok=True)
    joblib.dump(
        {
            "model": model,
            "classes": classes,
            "embed_model": EMBED_MODEL,
            "dim": DIM,
            "sklearn_version": sklearn.__version__,
            "manifest_sha256": hashlib.sha256(MANIFEST.read_bytes()).hexdigest(),
            "trained_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
        MODEL_PATH,
        compress=3,
    )

    print(f"fold 5: {summary['test_clips']} clips")
    print(f"  accuracy (argmax)         {summary['accuracy_argmax']:.3f}")
    print(f"  accuracy (p > {MIN_PROB} gate)    {summary['accuracy_with_gate']:.3f}")
    print(f"  'other' clips that fired  {summary['other_clips_false_alarm_rate']:.3f}")
    for label, recall in per_class.items():
        print(f"  recall {label:24s} {recall:.3f}")
    print(f"saved {MODEL_PATH.relative_to(ROOT)}; results in eval/results/")


if __name__ == "__main__":
    main()
