"""Corpus evidence, grouping, publication and replay tests using synthetic fixtures only."""
from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import corpus
import embed_corpus
import embedding_core as core
from dataset_io import read_csv, write_json
from export_corpus_replay import export
from test_pipeline import write_wav
from mock_cli import Client
from validate_dataset import validate


class CorpusTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "raw").mkdir()
        self.input = self.root / "raw/input.json"

    def source(self, index: int = 0, label: str = "builtin_smoke_alarm") -> dict[str, object]:
        path = self.root / f"raw/take{index}.wav"
        samples = np.zeros(7 * corpus.RATE + 4000, dtype=np.int16)
        samples[corpus.RATE:4 * corpus.RATE] = 100 + index
        samples[6 * corpus.RATE:] = 200 + index
        write_wav(path, samples)
        return {"clip_id": f"take{index}", "path": str(path), "label": label,
                "source_group": f"independent-take-{index}", "capture_kind": "direct_capture",
                "license": "consented-private", "source_url": None, "author": "fixture",
                "attribution": "Synthetic test fixture, never publish as collected evidence.",
                "downloaded_at": None, "consent_status": "granted", "consent_ref": "test-only",
                "recorded_at": "2026-10-25T08:00:00-04:00", "device": "test-mic", "room": "test-room",
                "distance_m": 1, "position": "near", "door_position": "open", "background": "quiet",
                "event_variation": "fixture", "alarm_pattern": "T3" if label == "builtin_smoke_alarm" else None,
                "tone_hz": None, "windowing": "isolated", "lineage": [],
                "events": [{"at_seconds": 1, "end_seconds": 4, "sound_id": label, "expected_alert": True},
                           {"at_seconds": 6, "end_seconds": 7.25, "sound_id": label, "expected_alert": True}] if label in corpus.BUILTINS else []}

    def prepare(self, sources: list[dict[str, object]], dataset: str = "smoke_alarm") -> Path:
        write_json(self.input, {"version": 1, "sources": sources})
        return corpus.prepare(self.input, dataset, self.root)

    def test_format_offsets_and_continuous_chronology(self) -> None:
        source = self.source(label="typing")
        source["windowing"] = "continuous"
        manifest = self.prepare([source], "regression")
        rows, companions = corpus.read_prepared(manifest, "regression")
        self.assertEqual([r["fold"] for r in rows], ["", ""])
        metadata = json.loads(companions[0].read_text())
        self.assertEqual([c["offset_samples"] for c in metadata["clips"].values()], [0, 48000])
        self.assertEqual(metadata["sources"]["take0"]["trailing_seconds"], 1.25)
        self.assertEqual(self.prepare([source], "regression"), manifest)
        self.assertFalse(json.loads(companions[1].read_text())["collection_target_met"])

    def test_invalid_provenance_audio_and_annotations(self) -> None:
        source = self.source()
        changes = [{"license": "CC-BY-NC-4.0"}, {"consent_status": "pending"},
                   {"consent_ref": None}, {"distance_m": -1}, {"alarm_pattern": "T4"},
                   {"capture_kind": "simulation"}, {"events": [{"at_seconds": 90, "sound_id": "builtin_smoke_alarm", "expected_alert": True}]},
                   {"path": "/tmp/not-an-allowed-recording.wav"}]
        for change in changes:
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.prepare([source | change])
        with self.assertRaises(ValueError):
            self.prepare([source, source])
        del source["author"]
        with self.assertRaisesRegex(ValueError, "Missing source fields"):
            self.prepare([source])
        for samples in [np.zeros(48000), np.ones(50)]:
            source = self.source()
            write_wav(Path(source["path"]), samples)
            with self.assertRaises(ValueError):
                self.prepare([source])

    def test_public_license_and_unknown_metadata(self) -> None:
        source = self.source() | {"license": "CC0-1.0", "capture_kind": "public_recording",
                                  "source_url": "https://example.org/fixture", "downloaded_at": "2026-10-25",
                                  "consent_status": "not_applicable", "consent_ref": None,
                                  "device": None, "recorded_at": None, "room": None}
        manifest = self.prepare([source])
        corpus.read_prepared(manifest, "smoke_alarm")
        with self.assertRaises(ValueError):
            self.prepare([source | {"downloaded_at": None}])

    def test_folds_union_duplicates_lineage_and_co_exclusion(self) -> None:
        sources = [self.source(i) for i in range(10)]
        manifest = self.prepare(sources)
        metadata = json.loads(manifest.with_name("smoke_alarm_metadata.json").read_text())
        values = list(metadata["sources"].values())
        folds = corpus.assign_folds(values, "smoke_alarm")
        self.assertEqual(set(folds.values()), {"1", "2", "3", "4", "5"})
        self.assertEqual(folds, corpus.assign_folds(list(reversed(values)), "smoke_alarm"))
        values[1]["source_sha256"] = values[0]["source_sha256"]
        values[2]["lineage"] = [values[0]["source_group"]]
        values[2]["label"] = "co_alarm"
        folds = corpus.assign_folds(values, "smoke_alarm")
        self.assertEqual([folds[f"take{i}"] for i in range(3)], ["", "", ""])

    def test_tampering_and_overlap(self) -> None:
        source = self.source()
        smoke = self.prepare([source])
        (self.root / "manifests").mkdir()
        (self.root / "manifests/smoke_alarm_metadata.json").write_bytes(smoke.with_name("smoke_alarm_metadata.json").read_bytes())
        regression = self.prepare([source], "regression")
        self.assertEqual(corpus.overlap(regression, "regression", self.root)["shared_sources"], ["take0"])
        metadata_path = regression.with_name("regression_metadata.json")
        metadata = json.loads(metadata_path.read_text())
        metadata["clips"]["take0__000000"]["source_sha256"] = "0" * 64
        write_json(metadata_path, metadata)
        with self.assertRaises(ValueError):
            corpus.read_prepared(regression, "regression")

    def test_smoke_gate_cache_publication_and_preserved_previous_bundle(self) -> None:
        manifest = self.prepare([self.source(i) for i in range(6)])
        rows = read_csv(manifest)
        cache = self.root / "raw/cache"
        cache.mkdir()
        vector = np.ones(768, dtype=np.float32) / np.sqrt(np.float32(768))
        for row in rows:
            core.save_array(cache / f"{core.fingerprint(row, Path(row['path']).read_bytes())}.npy", vector)
        with redirect_stdout(io.StringIO()), patch.object(core, "new_client", side_effect=AssertionError("No API request allowed")):
            with self.assertRaisesRegex(ValueError, "twice"):
                embed_corpus.run(manifest, "smoke_alarm", False, False, self.root, cache)
            for _ in range(2):
                embed_corpus.run(manifest, "smoke_alarm", True, False, self.root, cache)
            embed_corpus.run(manifest, "smoke_alarm", False, False, self.root, cache)
            result = validate("smoke_alarm", self.root)
            self.assertEqual(result["status"], "complete")
            self.assertFalse(result["ready_for_issue_closure"])
            published = self.root / "embeddings/smoke_alarm_768.npy"
            previous = published.read_bytes()
            last_key = core.fingerprint(rows[-1], Path(rows[-1]["path"]).read_bytes())
            (cache / f"{last_key}.npy").unlink()
            with self.assertRaises(AssertionError):
                embed_corpus.run(manifest, "smoke_alarm", False, False, self.root, cache)
            self.assertEqual(published.read_bytes(), previous)

    def test_replay_export_is_private_and_preserves_original_duration(self) -> None:
        manifest = self.prepare([self.source(label="builtin_door_knock")], "regression")
        destination = self.root / "raw/replay.json"
        export(manifest, destination, self.root)
        bundle = json.loads(destination.read_text())
        self.assertEqual(bundle["trials"][0]["duration_seconds"], 7.25)
        self.assertIn("wav_base64", bundle["trials"][0])
        with self.assertRaises(ValueError):
            export(manifest, self.root / "public.json", self.root)

    def test_interrupted_embedding_resumes_then_passes_cache_gate(self) -> None:
        manifest = self.prepare([self.source(i, "typing") for i in range(6)], "regression")
        cache = self.root / "raw/cache"
        log = self.root / "raw/requests.txt"
        with redirect_stdout(io.StringIO()), patch.object(core.RateLimiter, "wait"):
            with patch.object(core, "new_client", lambda: Client(log, 2)):
                with self.assertRaises(RuntimeError):
                    embed_corpus.run(manifest, "regression", True, False, self.root, cache)
            self.assertEqual(len(list(cache.glob("*.npy"))), 2)
            with patch.object(core, "new_client", lambda: Client(log, None)):
                embed_corpus.run(manifest, "regression", True, False, self.root, cache)
                embed_corpus.run(manifest, "regression", True, False, self.root, cache)
                embed_corpus.run(manifest, "regression", False, False, self.root, cache)
            self.assertEqual(len(log.read_text().splitlines()), 6)
            self.assertEqual(validate("regression", self.root)["status"], "complete")
            # Published hashes and vectors remain verifiable on a teammate's
            # machine even when none of the private audio has been restored.
            (self.root / "raw").rename(self.root / "raw-not-restored")
            report = validate("regression", self.root)
            self.assertEqual(report["status"], "complete")
            self.assertFalse(report["audio_verified"])

    def test_collection_counts_independent_groups_and_one_primary_device(self) -> None:
        source = self.source(label="typing")
        sources = []
        for index in range(5):
            copy = source | {"clip_id": f"take{index}", "source_group": f"group{index}",
                             "source_sha256": str(index) * 64, "device": f"phone{index}"}
            sources.append(copy)
        quality = corpus.coverage(sources, "regression")
        self.assertEqual(quality["target_deficits"]["typing/near"], 4)
        for item in sources:
            item["source_sha256"] = "a" * 64
            item["device"] = "phone0"
        quality = corpus.coverage(sources, "regression")
        self.assertEqual(quality["target_deficits"]["typing/near"], 4)

    def test_sustained_smoke_requires_intervals_and_excludes_baseline(self) -> None:
        source = self.source()
        source["windowing"] = "sustained"
        for event in source["events"]:
            event.pop("end_seconds")
        with self.assertRaisesRegex(ValueError, "event ends"):
            self.prepare([source])
        source["events"] = [{"at_seconds": 3.1, "end_seconds": 5.9,
                              "sound_id": "builtin_smoke_alarm", "expected_alert": True}]
        manifest = self.prepare([source])
        rows, companions = corpus.read_prepared(manifest, "smoke_alarm")
        self.assertEqual(len(rows), 1)
        metadata = json.loads(companions[0].read_text())
        self.assertEqual(metadata["clips"][rows[0]["clip_id"]]["offset_samples"], 48000)
        self.assertEqual(metadata["sources"]["take0"]["annotation_excluded_seconds"], 3)

    def test_public_training_selection_caps_windows_without_gain_changes(self) -> None:
        source = self.source()
        write_wav(Path(source["path"]), np.repeat(np.array([100, 900, 500], dtype=np.int16), 48000))
        source.update(windowing="sustained", max_windows=2, window_selection="highest_energy",
                      events=[{"at_seconds": 0, "end_seconds": 9, "sound_id": "builtin_smoke_alarm", "expected_alert": True}])
        manifest = self.prepare([source])
        rows, companions = corpus.read_prepared(manifest, "smoke_alarm")
        metadata = json.loads(companions[0].read_text())
        self.assertEqual([metadata["clips"][row["clip_id"]]["offset_samples"] for row in rows], [48000, 96000])
        from convert import validate_wav
        self.assertEqual(int(np.frombuffer(validate_wav(Path(rows[0]["path"])), dtype="<i2")[0]), 900)
        metadata["sources"]["take0"]["accepted_windows"] = 999
        write_json(companions[0], metadata)
        with self.assertRaisesRegex(ValueError, "Accepted-window counts"):
            corpus.read_prepared(manifest, "smoke_alarm")
        with self.assertRaisesRegex(ValueError, "chronological"):
            self.prepare([source], "regression")


if __name__ == "__main__":
    unittest.main()
