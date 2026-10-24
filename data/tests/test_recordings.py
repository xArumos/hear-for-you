"""Recording ingestion and complete CLI flows using isolated synthetic fixtures."""
from __future__ import annotations

from contextlib import redirect_stdout
import io
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from convert import RATE, SAMPLES, validate_wav
from dataset_io import DATA, FIELDS, atomic_bytes, manifest_bytes, read_csv, sha256_file, write_json
import embedding_core as core
import prepare_recordings as preparation
from test_pipeline import Clock, write_wav


class RecordingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.raw = self.root / "raw"
        self.raw.mkdir()
        self.input = self.raw / "input.csv"

    def sources(self) -> list[dict[str, str]]:
        rows = []
        for index, label in enumerate(["desk_bell", "builtin_door_knock", "appliance_beep"]):
            path = self.raw / f"take{index}.wav"
            samples = np.zeros(5 * RATE, dtype=np.int16)
            samples[RATE:4 * RATE] = (index + 1) * 100
            write_wav(path, samples)
            rows.append(dict(zip(FIELDS, [f"take{index}", str(path), label, "ours", "",
                            "2026-10-24T08:00:00-04:00", "test-microphone"], strict=True)))
        background = self.raw / "background.wav"
        # Two accepted windows, one wholly silent window, then 0.5 s trailing audio.
        samples = np.concatenate((np.full(SAMPLES, 100), np.zeros(SAMPLES),
                                  np.full(SAMPLES, 300), np.full(RATE // 2, 200)))
        write_wav(background, samples)
        rows.append(dict(zip(FIELDS, ["room", str(background), "background", "ours", "",
                        "2026-10-24T08:00:00-04:00", "test-microphone"], strict=True)))
        atomic_bytes(self.input, manifest_bytes(rows))
        return rows

    def prepare(self) -> list[dict[str, str]]:
        with redirect_stdout(io.StringIO()):
            return preparation.prepare(self.input, self.root)

    def command(self, script: str, *args: str, mocked: bool = False,
                fail_after: int | None = None) -> subprocess.CompletedProcess[str]:
        command = [sys.executable]
        if mocked:
            command += [str(DATA / "tests/mock_cli.py"), "--call-log", str(self.root / "calls.txt"),
                        "--cache", str(self.raw / "cache")]
            if fail_after is not None:
                command += ["--fail-after", str(fail_after)]
        command += [str(DATA / script), *args]
        return subprocess.run(command, capture_output=True, text=True, timeout=30)

    def test_segmentation_provenance_quality_and_reproducibility(self) -> None:
        self.sources()
        rows = self.prepare()
        self.assertEqual(len(rows), 5)
        manifest = self.root / "manifests/recordings.csv"
        first = manifest.read_bytes()
        _, companions = preparation.read_prepared(manifest)
        metadata = json.loads(companions[0].read_text())
        quality = json.loads(companions[1].read_text())
        self.assertEqual(quality["background_accepted_seconds"], 6)
        self.assertEqual(quality["silent_excluded_seconds"], 3)
        self.assertEqual(quality["trailing_seconds"], 0.5)
        self.assertFalse(quality["collection_target_met"])
        self.assertEqual(quality["target_deficits"]["background_seconds"], 3594)
        background = [clip for clip in metadata["clips"] if clip["parent_clip_id"] == "room"]
        self.assertEqual([clip["offset_samples"] for clip in background], [0, 96000])
        self.assertEqual(background[0]["group_id"], background[1]["group_id"])
        takes = [clip for clip in metadata["clips"] if clip["parent_clip_id"] != "room"]
        self.assertTrue(all(clip["offset_samples"] == 16000 for clip in takes))
        self.assertEqual(rows[0]["recorded_at"], "2026-10-24T12:00:00Z")
        for row in rows:
            validate_wav(Path(row["path"]))
            self.assertEqual(row["fold"], "")
        mtimes = {row["path"]: Path(row["path"]).stat().st_mtime_ns for row in rows}
        self.prepare()
        self.assertEqual(manifest.read_bytes(), first)
        self.assertEqual(mtimes, {row["path"]: Path(row["path"]).stat().st_mtime_ns for row in rows})

    def test_invalid_input_metadata(self) -> None:
        base = self.sources()
        changes = [{"clip_id": "../unsafe"}, {"source": "esc50"}, {"fold": "1"},
                   {"recorded_at": "2026-10-24T08:00:00"}, {"recorded_at": "invalid"},
                   {"device": ""}, {"label": "builtin_smoke_alarm"}, {"path": "/tmp/missing.wav"}]
        for change in changes:
            atomic_bytes(self.input, manifest_bytes([base[0] | change]))
            with self.subTest(change=change), self.assertRaises(ValueError):
                preparation.read_sources(self.input, self.raw)
        atomic_bytes(self.input, manifest_bytes([base[0], base[0]]))
        with self.assertRaises(ValueError):
            preparation.read_sources(self.input, self.raw)
        atomic_bytes(self.input, manifest_bytes([]))
        with self.assertRaisesRegex(ValueError, "no recordings"):
            preparation.read_sources(self.input, self.raw)

    def test_short_corrupt_and_all_silent_preserve_previous_outputs(self) -> None:
        rows = self.sources()
        self.prepare()
        manifest = self.root / "manifests/recordings.csv"
        original = manifest.read_bytes()
        for samples in [np.ones(100), np.zeros(SAMPLES * 2)]:
            write_wav(Path(rows[0]["path"]), samples)
            atomic_bytes(self.input, manifest_bytes([rows[0]]))
            with self.assertRaises(ValueError):
                self.prepare()
            self.assertEqual(manifest.read_bytes(), original)
        Path(rows[0]["path"]).write_bytes(b"bad audio")
        with self.assertRaises(ValueError):
            self.prepare()
        self.assertEqual(manifest.read_bytes(), original)
        silent_background = rows[-1]
        write_wav(Path(silent_background["path"]), np.zeros(SAMPLES * 2))
        atomic_bytes(self.input, manifest_bytes([silent_background]))
        with self.assertRaisesRegex(ValueError, "No non-silent"):
            self.prepare()

    def test_changed_sources_and_tampered_prepared_audio(self) -> None:
        sources = self.sources()
        before = self.prepare()
        changed = np.full(5 * RATE, 600)
        write_wav(Path(sources[0]["path"]), changed)
        after = self.prepare()
        before_row = next(row for row in before if row["label"] == "desk_bell")
        after_row = next(row for row in after if row["label"] == "desk_bell")
        self.assertNotEqual(core.fingerprint(before_row, Path(before_row["path"]).read_bytes()),
                            core.fingerprint(after_row, Path(after_row["path"]).read_bytes()))
        write_wav(Path(after_row["path"]), np.full(SAMPLES, 10))
        with self.assertRaisesRegex(ValueError, "changed"):
            preparation.read_prepared(self.root / "manifests/recordings.csv")

    def test_cli_end_to_end_interrupt_resume_and_validate(self) -> None:
        self.sources()
        prepared = self.command("prepare_recordings.py", "--input", str(self.input), "--output-dir", str(self.root))
        self.assertEqual(prepared.returncode, 0, prepared.stderr)
        manifest = self.root / "manifests/recordings.csv"
        args = ["--manifest", str(manifest)]
        dry = self.command("embed_recordings.py", *args, "--smoke-test", "--dry-run")
        self.assertEqual(dry.returncode, 0, dry.stderr)
        blocked = self.command("embed_recordings.py", *args, "--full", mocked=True)
        self.assertNotEqual(blocked.returncode, 0)
        self.assertIn("twice", blocked.stderr)
        interrupted = self.command("embed_recordings.py", *args, "--smoke-test", mocked=True, fail_after=2)
        self.assertNotEqual(interrupted.returncode, 0)
        self.assertEqual(len(list((self.raw / "cache").glob("*.npy"))), 2)
        resumed = self.command("embed_recordings.py", *args, "--smoke-test", mocked=True)
        self.assertEqual(resumed.returncode, 0, resumed.stderr)
        self.assertIn("newly_embedded=3", resumed.stdout)
        second = self.command("embed_recordings.py", *args, "--smoke-test", mocked=True)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertIn("newly_embedded=0", second.stdout)
        completed = self.command("embed_recordings.py", *args, "--full", mocked=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual((self.root / "calls.txt").read_text().count("request"), 5)
        matrix = np.load(self.root / "embeddings/recordings_768.npy", allow_pickle=False)
        core.validate_matrix(matrix, 5)
        validated = self.command("validate_dataset.py", "--dataset", "recordings", "--output-dir", str(self.root))
        self.assertEqual(validated.returncode, 0, validated.stdout + validated.stderr)
        status = json.loads((self.raw / "status/recordings.json").read_text())
        self.assertTrue(status["audio_verified"])
        self.assertFalse(status["collection"]["collection_target_met"])
        rows = read_csv(manifest)
        for index, row in enumerate(rows):
            seed = int(hashlib.sha256(Path(row["path"]).read_bytes()).hexdigest()[:8], 16) % 1000 + 1
            np.testing.assert_array_equal(matrix[index], core.normalize(np.arange(768) + seed))
        matrix[[0, 1]] = matrix[[1, 0]]
        core.save_array(self.root / "embeddings/recordings_768.npy", matrix)
        tampered = self.command("validate_dataset.py", "--dataset", "recordings", "--output-dir", str(self.root))
        self.assertNotEqual(tampered.returncode, 0)
        matrix[[0, 1]] = matrix[[1, 0]]
        core.save_array(self.root / "embeddings/recordings_768.npy", matrix)
        first_audio = Path(rows[0]["path"])
        first_audio.rename(first_audio.with_suffix(".hidden"))
        partial = self.command("validate_dataset.py", "--dataset", "recordings", "--output-dir", str(self.root))
        self.assertNotEqual(partial.returncode, 0)
        first_audio.with_suffix(".hidden").rename(first_audio)
        for row in rows:
            Path(row["path"]).unlink()
        shared = self.command("validate_dataset.py", "--dataset", "recordings", "--output-dir", str(self.root))
        self.assertEqual(shared.returncode, 0, shared.stdout + shared.stderr)
        status = json.loads((self.raw / "status/recordings.json").read_text())
        self.assertFalse(status["audio_verified"])

    def test_metadata_hash_mismatch_and_insufficient_smoke_data(self) -> None:
        rows = self.sources()
        atomic_bytes(self.input, manifest_bytes(rows[:1]))
        self.prepare()
        manifest = self.root / "manifests/recordings.csv"
        result = self.command("embed_recordings.py", "--manifest", str(manifest), "--smoke-test")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("at least five", result.stderr)
        metadata = manifest.with_name("recordings_metadata.json")
        content = json.loads(metadata.read_text())
        content["manifest_sha256"] = "wrong"
        write_json(metadata, content)
        with self.assertRaisesRegex(ValueError, "stale"):
            preparation.read_prepared(manifest)

    def test_pacing_survives_restart(self) -> None:
        path = self.raw / "last-request.json"
        write_json(path, {"started_at": 100.0})
        clock = Clock()
        with patch.object(core.time, "time", return_value=100.2):
            limiter = core.RateLimiter(clock.time, clock.sleep, pacing_path=path)
            limiter.wait()
        self.assertAlmostEqual(clock.now, 0.8)
        self.assertEqual(json.loads(path.read_text())["started_at"], 100.2)

    def test_process_lock_prevents_parallel_runs(self) -> None:
        import fcntl
        self.sources()
        rows = self.prepare()
        manifest = self.root / "manifests/recordings.csv"
        cache = self.raw / "cache"
        cache.mkdir()
        with (cache / "run.lock").open("w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            with self.assertRaisesRegex(ValueError, "Another embedding"):
                core.run_dataset(rows, manifest, self.root, "recordings", rows, True, False, cache)


if __name__ == "__main__":
    unittest.main()
