"""Shared Gemini embedding, pacing, checkpoint and publication support."""
from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import fcntl
import hashlib
import io
import json
from pathlib import Path
import time

import numpy as np
from google import genai
from google.genai import errors, types

from convert import BACKGROUND_VERSION, CORPUS_PREPROCESS_VERSION, PREPROCESS_VERSION, validate_wav
from dataset_io import DATA, ROOT, atomic_bytes, manifest_bytes, sha256_file, write_json

MODEL = "gemini-embedding-2"
DIM = 768
CACHE = DATA / "raw/embedding-cache"

def normalize(values: object) -> np.ndarray:
    vector = np.asarray(values, dtype=np.float64)
    if vector.shape != (DIM,) or not np.all(np.isfinite(vector)):
        raise ValueError("Embedding must contain exactly 768 finite values.")
    norm = np.linalg.norm(vector)
    if not np.isfinite(norm) or norm == 0:
        raise ValueError("Embedding has invalid or zero norm.")
    return (vector / norm).astype(np.float32)


def valid_vector(vector: np.ndarray) -> bool:
    return (vector.shape == (DIM,) and vector.dtype == np.float32
            and bool(np.all(np.isfinite(vector)))
            and abs(float(np.linalg.norm(vector.astype(np.float64))) - 1) <= 1e-5)


def save_array(path: Path, array: np.ndarray) -> None:
    buffer = io.BytesIO()
    np.save(buffer, array, allow_pickle=False)
    atomic_bytes(path, buffer.getvalue())




def fingerprint(row: dict[str, str], wav: bytes) -> str:
    preprocessing = (CORPUS_PREPROCESS_VERSION if row.get("source") in {
        "direct_capture", "speaker_playback", "public_recording", "simulation"} else
        BACKGROUND_VERSION if row.get("source") == "ours" and row.get("label") == "background" else PREPROCESS_VERSION)
    identity = {"clip_id": row["clip_id"], "audio_sha256": hashlib.sha256(wav).hexdigest(),
                "model": MODEL, "dim": DIM, "preprocessing": preprocessing}
    return hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()


def load_cached(path: Path) -> np.ndarray | None:
    try:
        vector = np.load(path, allow_pickle=False)
        if not isinstance(vector, np.ndarray):
            vector.close()
            return None
        return vector if valid_vector(vector) else None
    except (OSError, ValueError, EOFError):
        return None


class RateLimiter:
    def __init__(self, clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep,
                 pacing_path: Path | None = None) -> None:
        self.clock = clock
        self.sleep = sleep
        self.next_start = 0.0
        self.pacing_path = pacing_path
        if pacing_path is not None:
            try:
                previous = float(json.loads(pacing_path.read_text())["started_at"])
                self.next_start = self.clock() + max(0.0, min(1.0, 1.0 - (time.time() - previous)))
            except (OSError, ValueError, KeyError, TypeError):
                self.next_start = self.clock() + 1.0

    def wait(self, delay: float = 0.0) -> None:
        target = max(self.next_start, self.clock() + delay)
        while self.clock() < target:
            self.sleep(min(60.0, target - self.clock()))
        self.next_start = self.clock() + 1.0
        if self.pacing_path is not None:
            write_json(self.pacing_path, {"started_at": time.time()})


def retry_delay(error: errors.APIError) -> float:
    delay = 1.0
    response = getattr(error, "response", None)
    header = response.headers.get("Retry-After") if response is not None else None
    if header:
        try:
            delay = max(delay, float(header))
        except ValueError:
            try:
                delay = max(delay, (parsedate_to_datetime(header) - datetime.now(timezone.utc)).total_seconds())
            except (ValueError, TypeError):
                pass
    payload = error.details
    if isinstance(payload, dict):
        error_payload = payload.get("error", payload)
        details = error_payload.get("details", []) if isinstance(error_payload, dict) else []
        if isinstance(details, list):
            for item in details:
                if isinstance(item, dict):
                    value = item.get("retryDelay", "")
                    if isinstance(value, str) and value.endswith("s"):
                        try:
                            delay = max(delay, float(value[:-1]))
                        except ValueError:
                            pass
    return delay


def request_vector(client: genai.Client, wav: bytes, clip_id: str,
                   limiter: RateLimiter) -> np.ndarray:
    delay = 0.0
    for attempt in (1, 2):
        limiter.wait(delay)
        start = limiter.clock()
        status = "failed"
        try:
            result = client.models.embed_content(
                model=MODEL,
                contents=types.Content(parts=[types.Part.from_bytes(data=wav, mime_type="audio/wav")]),
                config=types.EmbedContentConfig(output_dimensionality=DIM),
            )
            if not result.embeddings or len(result.embeddings) != 1:
                raise ValueError("Expected one embedding per clip.")
            vector = normalize(result.embeddings[0].values)
            status = "ok"
            return vector
        except errors.APIError as exc:
            status = str(exc.code)
            if attempt == 1 and (exc.code == 429 or 500 <= exc.code < 600):
                delay = retry_delay(exc)
                print(f"clip={clip_id} retry_after_s={delay:g}", flush=True)
                continue
            raise RuntimeError(f"clip={clip_id}: Gemini HTTP {exc.code}; checkpoint preserved.") from None
        except Exception as exc:
            raise RuntimeError(f"clip={clip_id}: {type(exc).__name__}; checkpoint preserved.") from None
        finally:
            print(f"clip={clip_id} attempt={attempt} status={status} "
                  f"latency_ms={round((limiter.clock() - start) * 1000)}", flush=True)
    raise RuntimeError("Retry exhausted.")


def read_key(path: Path = ROOT / "api/.env") -> str:
    try:
        for line in path.read_text().splitlines():
            name, separator, value = line.strip().partition("=")
            if separator and name.strip() == "GEMINI_API_KEY":
                value = value.strip().strip("\"'")
                if value and value != "your-key-here":
                    return value
    except FileNotFoundError:
        pass
    raise ValueError("Set GEMINI_API_KEY in api/.env before live embedding; no key was found.")


def new_client() -> genai.Client:
    return genai.Client(api_key=read_key(), http_options=types.HttpOptions(
        timeout=10_000, retry_options=types.HttpRetryOptions(attempts=1)))




def embed_rows(rows: list[dict[str, str]], cache: Path = CACHE,
               client_factory: Callable[[], genai.Client] | None = None) -> tuple[np.ndarray, int, list[str]]:
    # Validate every input before making any billable request.
    if not rows:
        raise ValueError("No clips selected for embedding.")
    inputs = []
    for row in rows:
        path = ROOT / row["path"]
        validate_wav(path)
        wav = path.read_bytes()
        inputs.append((row, path, fingerprint(row, wav)))
    cache.mkdir(parents=True, exist_ok=True)
    client = None
    limiter = RateLimiter(pacing_path=cache / "last-request.json")
    vectors = []
    requests = 0
    try:
        for row, audio_path, identity in inputs:
            wav = audio_path.read_bytes()
            if fingerprint(row, wav) != identity:
                raise ValueError("Audio changed during embedding; rerun preparation.")
            path = cache / f"{identity}.npy"
            vector = load_cached(path)
            if vector is None:
                if client is None:
                    client = (client_factory or new_client)()
                vector = request_vector(client, wav, row["clip_id"], limiter)
                requests += 1
                save_array(path, vector)
            else:
                print(f"clip={row['clip_id']} status=cached", flush=True)
            vectors.append(vector)
    finally:
        if client is not None:
            client.close()
    return np.stack(vectors), requests, [item[2] for item in inputs]



def checked_inputs(rows: list[dict[str, str]]) -> list[str]:
    keys = []
    for row in rows:
        path = ROOT / row["path"]
        validate_wav(path)
        keys.append(fingerprint(row, path.read_bytes()))
    return keys


def validate_matrix(matrix: np.ndarray, count: int) -> None:
    if (matrix.shape != (count, DIM) or matrix.dtype != np.float32
            or not all(valid_vector(vector) for vector in matrix)):
        raise ValueError("Matrix must have one finite float32 unit vector of size 768 per row.")


def artifact_report(rows: list[dict[str, str]], manifest: Path, matrix: np.ndarray,
                    matrix_path: Path, keys: list[str], new_count: int,
                    companions: list[Path]) -> dict[str, object]:
    validate_matrix(matrix, len(rows))
    norms = np.linalg.norm(matrix.astype(np.float64), axis=1)
    return {
        "status": "complete", "model": MODEL, "dimensions": DIM,
        "manifest_sha256": sha256_file(manifest), "matrix_sha256": sha256_file(matrix_path),
        "rows": len(rows), "labels": dict(Counter(row["label"] for row in rows)),
        "duration_seconds": len(rows) * 3, "shape": list(matrix.shape),
        "dtype": str(matrix.dtype), "norm_min": float(norms.min()), "norm_max": float(norms.max()),
        "clip_fingerprints": keys, "newly_embedded": new_count,
        "companions": {path.name: sha256_file(path) for path in companions},
    }


def run_dataset(rows: list[dict[str, str]], manifest: Path, output_dir: Path,
                dataset: str, smoke_selection: list[dict[str, str]], smoke: bool,
                dry_run: bool, cache: Path = CACHE, companions: list[Path] | None = None) -> None:
    """Gate full runs, serialize API use, and publish only complete artifacts."""
    companions = companions or []
    selected = smoke_selection if smoke else rows
    if not selected:
        raise ValueError("No clips selected; prepare recordings first.")
    if dry_run:
        checked_inputs(selected)
        print(f"Dry run: {len(selected)} valid WAVs; model={MODEL}, dim={DIM}; no API requests.")
        return
    if len(smoke_selection) != 5:
        raise ValueError("At least five prepared clips are required for the smoke-test gate.")
    cache.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / (f"raw/smoke/{dataset}/validation.json" if smoke
                                else f"reports/{dataset}_validation.json")
    mode = "smoke" if smoke else "full"
    attempt_path = output_dir / f"raw/status/{dataset}_{mode}_attempt.json"
    with (cache / "run.lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("Another embedding process is running.") from None
        manifest_hash = sha256_file(manifest)
        companion_hashes = {path.name: sha256_file(path) for path in companions}
        receipt_path = cache / f"{dataset}-smoke-passed.json"
        try:
            if not smoke:
                try:
                    receipt = json.loads(receipt_path.read_text())
                except (OSError, ValueError):
                    receipt = {}
                smoke_keys = checked_inputs(smoke_selection)
                expected = {"manifest_sha256": manifest_hash, "keys": smoke_keys,
                            "companions": companion_hashes, "cache_only": True}
                if (receipt != expected or any(load_cached(cache / f"{key}.npy") is None
                                               for key in smoke_keys)):
                    raise ValueError("Run --smoke-test twice successfully before --full.")
            matrix, new_count, keys = embed_rows(selected, cache)
            validate_matrix(matrix, len(selected))
            if (sha256_file(manifest) != manifest_hash or checked_inputs(selected) != keys
                    or {path.name: sha256_file(path) for path in companions} != companion_hashes):
                raise ValueError("Dataset changed during embedding; rerun preparation.")
            matrix_path = output_dir / (f"raw/smoke/{dataset}/embeddings.npy" if smoke
                                        else f"embeddings/{dataset}_768.npy")
            save_array(matrix_path, matrix)
            if smoke:
                atomic_bytes(matrix_path.parent / "manifest.csv", manifest_bytes(selected))
                write_json(receipt_path, {"manifest_sha256": manifest_hash, "keys": keys,
                           "companions": companion_hashes, "cache_only": new_count == 0})
            report = artifact_report(selected, manifest, matrix, matrix_path, keys, new_count, companions)
            write_json(report_path, report)
            write_json(attempt_path, {"status": "complete", "model": MODEL,
                       "manifest_sha256": manifest_hash, "rows": len(selected)})
            print(f"Complete: shape={matrix.shape}, dtype={matrix.dtype}, newly_embedded={new_count}.")
        except (OSError, ValueError, RuntimeError) as exc:
            write_json(attempt_path, {"status": "incomplete", "model": MODEL,
                       "manifest_sha256": manifest_hash, "rows": len(selected),
                       "reason": str(exc)})
            raise


def verify_artifacts(rows: list[dict[str, str]], manifest: Path, matrix_path: Path,
                     report_path: Path, companions: list[Path] | None = None) -> dict[str, object]:
    """Verify a published matrix and its provenance without needing a key."""
    report = json.loads(report_path.read_text())
    matrix = np.load(matrix_path, allow_pickle=False)
    if not isinstance(matrix, np.ndarray):
        matrix.close()
        raise ValueError("Expected a NumPy array, not an archive.")
    validate_matrix(matrix, len(rows))
    if (report.get("status") != "complete" or report.get("model") != MODEL
            or report.get("dimensions") != DIM
            or report.get("manifest_sha256") != sha256_file(manifest)
            or report.get("matrix_sha256") != sha256_file(matrix_path)
            or report.get("rows") != len(rows)
            or report.get("labels") != dict(Counter(row["label"] for row in rows))
            or report.get("companions") != {p.name: sha256_file(p) for p in companions or []}):
        raise ValueError("Published manifest, matrix, report, or provenance does not match.")
    keys = report.get("clip_fingerprints")
    if not isinstance(keys, list) or len(keys) != len(rows):
        raise ValueError("Missing row fingerprints.")
    available = [bool((ROOT / row["path"]).is_file()) for row in rows]
    if any(available) and not all(available):
        raise ValueError("Some audio files are missing; restore them before local validation.")
    if all(available) and checked_inputs(rows) != keys:
        raise ValueError("Audio differs from the published embedding fingerprints.")
    return report | {"audio_verified": all(available)}
