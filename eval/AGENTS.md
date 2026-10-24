# eval/AGENTS.md — evaluation rules (owner: P1)

Read the root `AGENTS.md` first. This folder produces every number judges see. If a number isn't reproducible from here, it doesn't go on the Model Card.

## Layout

```
eval/
  train_builtin.py     # trains the built-in classifier → api/models/builtin_clf.joblib
  zero_shot.py         # text-prompt baseline on the same test fold
  few_shot.py          # personal detector: leave-one-out threshold tuning, miss rate
  false_alarms.py      # runs 60 min of background embeddings through the detectors
  latency.py           # parses timed logs from the integration run
  write_metrics.py     # combines results → api/metrics.json (shape in CONTRACT.md)
  results/             # CSV outputs (committed)
  notebooks/           # optional exploration; scripts are the source of truth
```

## Rules

- Inputs are the committed embeddings in `data/embeddings/` and manifests in `data/manifests/`. Never call Gemini from eval scripts; `data/` scripts do the embedding.
- ESC-50: train on folds 1–4, test on fold 5. Never tune on fold 5.
- Built-in classes map from ESC-50 as listed in `data/README.md`; everything else is "other".
- Calibrate built-in probabilities on a held-out slice of the training folds (scikit-learn `CalibratedClassifierCV`).
- Always report the zero-shot baseline next to the trained number.
- Also report accuracy on our own venue recordings (ESC-50 has a known leakage caveat).
- Fix random seeds (`seed = 42`). Each script prints its numbers and writes a CSV to `results/`.
- `write_metrics.py` must output exactly the `/api/metrics` shape in `CONTRACT.md`, with `updated_at`.
- After updating numbers, also update `docs/MODEL_CARD.md` in the same PR.

## Run order

```bash
cd eval
uv run python train_builtin.py
uv run python zero_shot.py
uv run python few_shot.py
uv run python false_alarms.py
uv run python write_metrics.py
```
