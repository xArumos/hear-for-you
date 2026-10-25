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
  eval_relevance.py    # unknown-gate and pipeline false positives / misses on held-out ESC-50 clips
  eval_knock.py        # door-knock cutoff and retraining options vs. footsteps/typing/tapping (issue #27)
  write_metrics.py     # combines results → api/metrics.json (shape in CONTRACT.md)
  results/             # CSV outputs (committed)
  notebooks/           # optional exploration; scripts are the source of truth
```

## Rules

- Inputs are the committed embeddings in `data/embeddings/` and manifests in `data/manifests/`. Never call Gemini from eval scripts; `data/` scripts do the embedding. Two exceptions: `eval_relevance.py` calls the describe model (and embeds the same clips), because a relevance judgement can't be precomputed; `eval_knock.py` embeds ESC-50 household clips and noisy knocks that `data/` doesn't cover, caching vectors in ignored `data/raw/eval-cache/`. Both pace themselves under the free-tier limits and resume without repeating calls.
- ESC-50: train on folds 1–4, test on fold 5. Never tune on fold 5.
- Built-in classes map from ESC-50 as listed in `data/README.md`; everything else is "other".
- Calibrate built-in probabilities on a held-out slice of the training folds (scikit-learn `CalibratedClassifierCV`).
- Always report the zero-shot baseline next to the trained number.
- Also report accuracy on our own venue recordings (ESC-50 has a known leakage caveat).
- Fix random seeds (`seed = 42`). Each script prints its numbers and writes a CSV to `results/`.
- `write_metrics.py` must output exactly the `/api/metrics` shape in `CONTRACT.md`, with `updated_at`.
- After updating numbers, also update `docs/MODEL_CARD.md` in the same PR.

## Run order

eval/ uses api/'s environment, so the saved model matches the scikit-learn version the API loads it with.

```bash
cd eval
uv run --project ../api python train_builtin.py
uv run --project ../api python zero_shot.py
uv run --project ../api python few_shot.py
uv run --project ../api python false_alarms.py
uv run --project ../api python eval_relevance.py   # calls Gemini: ~100 describe + ~100 embed calls
uv run --project ../api python eval_knock.py       # calls Gemini once: ~310 embed calls, then cached
uv run --project ../api python write_metrics.py
```
