"""Offline behavior tests; no test makes a model request."""
from __future__ import annotations

from collections import Counter
from contextlib import redirect_stdout
import csv
import io
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import wave
import zipfile

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import convert
import download_esc50 as dataset
import embedding_core as embedding
import embed_esc50 as esc50
from google.genai import errors


def write_wav(path: Path, samples: np.ndarray, rate: int = 16000,
              channels: int = 1) -> None:
    with wave.open(str(path), "wb") as audio:
        audio.setparams((channels, 2, rate, len(samples) // channels, "NONE", "not compressed"))
        audio.writeframes(samples.astype("<i2").tobytes())


def metadata() -> list[dict[str, str]]:
    categories = sorted(dataset.BUILTINS) + ["clock_alarm"] + [f"other_{i:02}" for i in range(44)]
    return [{"filename": f"{fold}-{category}-{n}.wav", "category": category, "fold": str(fold)}
            for category in categories for fold in range(1, 6) for n in range(8)]


class AudioTests(unittest.TestCase):
    def test_loudest_is_exact_not_coarse_and_no_overflow(self) -> None:
        audio = np.zeros(80000, dtype=np.int16)
        audio[12345:12345 + 48000] = -32768
        chosen = convert.loudest_window(audio)
        np.testing.assert_array_equal(chosen, audio[12345:60345])

    def test_earliest_tie(self) -> None:
        audio = np.tile(np.array([100, -100], dtype=np.int16), 40000)
        np.testing.assert_array_equal(convert.loudest_window(audio), audio[:48000])

    def test_reject_short_silent_and_invalid(self) -> None:
        for samples in [np.ones(47999, dtype=np.int16), np.zeros(80000, dtype=np.int16)]:
            with self.assertRaises(ValueError):
                convert.loudest_window(samples)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.wav"
            path.write_bytes(b"not a wav")
            with self.assertRaises(ValueError):
                convert.validate_wav(path)
            write_wav(path, np.ones(48000), rate=8000)
            with self.assertRaises(ValueError):
                convert.validate_wav(path)

    def test_ffmpeg_user_facing_conversion(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source, target = Path(directory) / "stereo.wav", Path(directory) / "clip.wav"
            t = np.arange(5 * 44100) / 44100
            signal = (6000 * np.sin(2 * np.pi * 440 * t)).astype(np.int16)
            write_wav(source, np.repeat(signal, 2), rate=44100, channels=2)
            result = subprocess.run([sys.executable, str(dataset.DATA / "convert.py"),
                                     str(source), str(target)], capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            pcm = convert.validate_wav(target)
            self.assertEqual(len(pcm), 96000)
            self.assertLessEqual(np.abs(np.frombuffer(pcm, dtype="<i2")).max(), 6100)
            source.write_bytes(b"invalid")
            with self.assertRaises(ValueError):
                convert.convert_audio(source, target)
            self.assertEqual(target.read_bytes()[44:], pcm)


class SelectionTests(unittest.TestCase):
    def test_fresh_download_cli_and_cached_rerun(self) -> None:
        rows = metadata()
        csv_output = io.StringIO(newline="")
        writer = csv.DictWriter(csv_output, fieldnames=["filename", "category", "fold"])
        writer.writeheader()
        writer.writerows(rows)
        audio_output = io.BytesIO()
        with wave.open(audio_output, "wb") as audio:
            audio.setparams((1, 2, 44100, 220500, "NONE", "not compressed"))
            audio.writeframes(np.full(220500, 100, dtype="<i2").tobytes())
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            fixture = workspace / "official-fixture.zip"
            prefix = f"ESC-50-{dataset.REVISION}/"
            with zipfile.ZipFile(fixture, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr(prefix + "meta/esc50.csv", csv_output.getvalue())
                for row in dataset.select_rows(rows):
                    archive.writestr(prefix + "audio/" + row["filename"], audio_output.getvalue())
            # Exercise both CLI runs in a fresh workspace, replacing only the download transport.
            script = """
from pathlib import Path
import sys
from unittest.mock import patch
sys.path.insert(0, sys.argv[1])
import download_esc50 as dataset
dataset.ROOT = Path(sys.argv[2])
dataset.DATA = dataset.ROOT / 'data'
fixture = Path(sys.argv[3])
sys.argv = ['download_esc50.py', '--smoke-test']
with patch.object(dataset.urllib.request, 'urlopen', side_effect=lambda *a, **k: fixture.open('rb')) as fetch:
    dataset.main()
    dataset.main()
    assert fetch.call_count == 1, 'Cached rerun downloaded the archive again'
"""
            result = subprocess.run(
                [sys.executable, "-c", script, str(dataset.DATA), str(workspace), str(fixture)],
                capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            raw = workspace / "data/raw"
            archive_path = raw / f"esc50-{dataset.REVISION}.zip"
            self.assertEqual(archive_path.read_bytes(), fixture.read_bytes())
            self.assertFalse(archive_path.with_suffix(".zip.part").exists())
            self.assertEqual(len(list((raw / "esc50/audio").glob("*.wav"))), 260)
            converted = list((raw / "converted").glob("*.wav"))
            self.assertEqual(len(converted), 5)
            for path in converted:
                convert.validate_wav(path)
            from dataset_io import read_csv
            self.assertEqual(len(read_csv(workspace / "data/manifests/esc50.csv")), 260)

    def test_deterministic_balanced_and_preserves_folds(self) -> None:
        rows = metadata()
        chosen = dataset.select_rows(rows)
        self.assertEqual(chosen, dataset.select_rows(list(reversed(rows))))
        self.assertEqual(len(chosen), 260)
        self.assertEqual(len({r["filename"] for r in chosen}), 260)
        self.assertNotIn("clock_alarm", {r["category"] for r in chosen})
        other = [r for r in chosen if r["category"] not in dataset.BUILTINS]
        self.assertEqual(Counter(r["fold"] for r in other), {str(f): 12 for f in range(1, 6)})
        self.assertEqual(len({r["category"] for r in other}), 44)
        self.assertEqual(set(Counter(r["category"] for r in other).values()), {1, 2})
        original = {r["filename"]: r["fold"] for r in rows}
        self.assertTrue(all(original[r["filename"]] == r["fold"] for r in chosen))

    def test_unsafe_archive(self) -> None:
        for name in ["../escape.wav", "/absolute", f"ESC-50-{dataset.REVISION}/../escape"]:
            output = io.BytesIO()
            with zipfile.ZipFile(output, "w") as archive:
                archive.writestr(name, b"bad")
            with zipfile.ZipFile(output) as archive, self.assertRaises(ValueError):
                dataset.validate_archive(archive)

    def test_real_manifest_alignment_when_available(self) -> None:
        if not esc50.MANIFEST.exists():
            self.skipTest("Run downloader to generate the real manifest.")
        rows = esc50.read_manifest()
        self.assertEqual(len(rows), 260)
        smoke = esc50.smoke_rows(rows)
        self.assertEqual({r["label"] for r in smoke}, set(dataset.BUILTINS.values()))
        self.assertTrue(all(int(r["fold"]) < 5 for r in smoke))
        for row in smoke:
            convert.validate_wav(dataset.ROOT / row["path"])


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


class FakeClient:
    def __init__(self, responses: list[object]) -> None:
        self.responses = iter(responses)
        self.models = self
        self.calls: list[dict[str, object]] = []
        self.closed = False

    def embed_content(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return response

    def close(self) -> None:
        self.closed = True


def response() -> SimpleNamespace:
    return SimpleNamespace(embeddings=[SimpleNamespace(values=list(range(768)))])


class EmbeddingTests(unittest.TestCase):
    def test_normalization_and_rejections(self) -> None:
        self.assertTrue(embedding.valid_vector(embedding.normalize(np.arange(768))))
        for values in [np.zeros(768), np.ones(767), np.full(768, np.nan), np.full(768, np.inf)]:
            with self.assertRaises(ValueError):
                embedding.normalize(values)

    def test_rate_limit_and_retry_delay(self) -> None:
        clock = Clock()
        limiter = embedding.RateLimiter(clock.time, clock.sleep)
        error = errors.APIError(429, {"error": {"details": [{"retryDelay": "3s"}]}},
                                SimpleNamespace(headers={"Retry-After": "5"}))
        client = FakeClient([error, response(), response()])
        with redirect_stdout(io.StringIO()):
            vector = embedding.request_vector(client, b"wav", "one", limiter)
            self.assertEqual(clock.now, 5)
            embedding.request_vector(client, b"wav", "two", limiter)
        self.assertEqual(clock.now, 6)
        self.assertTrue(embedding.valid_vector(vector))
        self.assertEqual(client.calls[0]["config"].output_dimensionality, 768)
        self.assertEqual(client.calls[0]["model"], "gemini-embedding-2")
        self.assertEqual(len(client.calls[0]["contents"].parts), 1)

    def test_retry_exhaustion_and_nonretryable(self) -> None:
        for code, calls in [(500, 2), (429, 2), (400, 1), (401, 1)]:
            error = errors.APIError(code, {"error": {"message": "secret must not be logged"}})
            client = FakeClient([error, error])
            clock = Clock()
            output = io.StringIO()
            with redirect_stdout(output), self.assertRaises(RuntimeError) as caught:
                embedding.request_vector(client, b"wav", "one", embedding.RateLimiter(clock.time, clock.sleep))
            self.assertEqual(len(client.calls), calls)
            self.assertNotIn("secret", str(caught.exception) + output.getvalue())

    def test_invalid_cache_formats(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.npy"
            for vector in [np.ones(768, dtype=np.float32), np.ones(767, dtype=np.float32),
                           np.full(768, np.nan, dtype=np.float32), np.zeros(768, dtype=np.float32),
                           embedding.normalize(np.ones(768)).astype(np.float64)]:
                embedding.save_array(path, vector)
                self.assertIsNone(embedding.load_cached(path))
            with path.open("wb") as handle:
                np.savez(handle, unexpected=np.ones(768))
            self.assertIsNone(embedding.load_cached(path))

    def test_timeout_and_sdk_retry_settings(self) -> None:
        with patch.object(embedding, "read_key", return_value="test-key"), patch.object(embedding.genai, "Client") as factory:
            embedding.new_client()
        options = factory.call_args.kwargs["http_options"]
        self.assertEqual(options.timeout, 10000)
        self.assertEqual(options.retry_options.attempts, 1)

    def test_checkpoint_recovery_invalidation_and_row_alignment(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rows = []
            for i in range(2):
                path = root / f"{i}.wav"
                write_wav(path, np.full(48000, i + 1))
                rows.append({"path": str(path), "clip_id": str(i)})
            cache = root / "cache"
            first = FakeClient([response(), ValueError("interruption")])
            with patch.object(embedding.RateLimiter, "wait"), redirect_stdout(io.StringIO()):
                with self.assertRaises(RuntimeError):
                    embedding.embed_rows(rows, cache, lambda: first)
                self.assertEqual(len(list(cache.glob("*.npy"))), 1)
                self.assertTrue(first.closed)
                second = FakeClient([SimpleNamespace(embeddings=[SimpleNamespace(values=[1.] * 768)])])
                matrix, count, keys = embedding.embed_rows(rows, cache, lambda: second)
                self.assertEqual(count, 1)
                self.assertEqual(matrix.shape, (2, 768))
                np.testing.assert_array_equal(matrix[0], embedding.normalize(np.arange(768)))
                np.testing.assert_array_equal(matrix[1], embedding.normalize(np.ones(768)))
                factory = unittest.mock.Mock(side_effect=AssertionError("must not call network"))
                again, count, _ = embedding.embed_rows(rows, cache, factory)
                self.assertEqual(count, 0)
                np.testing.assert_array_equal(matrix, again)
                self.assertNotEqual(embedding.fingerprint(rows[0], b"changed"), keys[0])
                with patch.object(embedding, "PREPROCESS_VERSION", "changed"):
                    self.assertNotEqual(embedding.fingerprint(rows[0], Path(rows[0]["path"]).read_bytes()), keys[0])
                (cache / f"{keys[1]}.npy").write_bytes(b"corrupt")
                repaired = FakeClient([response()])
                _, count, _ = embedding.embed_rows(rows, cache, lambda: repaired)
                self.assertEqual(count, 1)

    def test_full_gate_and_no_partial_publication(self) -> None:
        if not esc50.MANIFEST.exists():
            self.skipTest("Run downloader first.")
        rows = esc50.read_manifest()
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(esc50, "CACHE", Path(directory) / "cache"), patch.object(esc50, "DATA", Path(directory)), patch.object(esc50, "read_manifest", return_value=rows), self.assertRaisesRegex(ValueError, "twice"):
                esc50.run(smoke=False, dry_run=False)


    def test_smoke_receipt_then_full_atomic_publication(self) -> None:
        from dataset_io import atomic_bytes, manifest_bytes
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            cache = temporary / "cache"
            rows = []
            for index in range(5):
                path = temporary / f"{index}.wav"
                write_wav(path, np.full(48000, index + 1))
                rows.append(dict(zip(dataset.FIELDS, [str(index), str(path), "other", "ours", "", "", ""], strict=True)))
            manifest = temporary / "manifest.csv"
            atomic_bytes(manifest, manifest_bytes(rows))
            keys = embedding.checked_inputs(rows)
            matrix = np.stack([embedding.normalize(np.arange(768))] * 5)
            cache.mkdir()
            for key in keys:
                embedding.save_array(cache / f"{key}.npy", matrix[0])
            target = temporary / "embeddings/example_768.npy"
            def run(smoke: bool) -> None:
                embedding.run_dataset(rows, manifest, temporary, "example", rows, smoke, False, cache)
            with patch.object(embedding, "embed_rows", return_value=(matrix, 5, keys)), redirect_stdout(io.StringIO()):
                run(True)
            with self.assertRaisesRegex(ValueError, "twice"):
                run(False)
            with patch.object(embedding, "embed_rows", return_value=(matrix, 0, keys)), redirect_stdout(io.StringIO()):
                run(True)
            with patch.object(embedding, "embed_rows", side_effect=RuntimeError("interrupted")):
                with self.assertRaisesRegex(RuntimeError, "interrupted"):
                    run(False)
            self.assertFalse(target.exists())
            with patch.object(embedding, "embed_rows", return_value=(matrix, 0, keys)), redirect_stdout(io.StringIO()):
                run(False)
            np.testing.assert_array_equal(np.load(target, allow_pickle=False), matrix)
            with patch.object(embedding, "embed_rows", side_effect=RuntimeError("interrupted")):
                with self.assertRaises(RuntimeError):
                    run(False)
            np.testing.assert_array_equal(np.load(target, allow_pickle=False), matrix)

    def test_all_inputs_validated_before_any_request(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "good.wav"
            bad = root / "bad.wav"
            write_wav(first, np.ones(48000))
            bad.write_bytes(b"invalid")
            factory = unittest.mock.Mock(side_effect=AssertionError("must not call network"))
            rows = [{"clip_id": "one", "path": str(first)}, {"clip_id": "two", "path": str(bad)}]
            with self.assertRaises(ValueError):
                embedding.embed_rows(rows, root / "cache", factory)
            factory.assert_not_called()


if __name__ == "__main__":
    unittest.main()
