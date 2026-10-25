"""Pinned acquisition checks, with no network requests or genuine recordings."""
from __future__ import annotations

from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fetch_public_corpus import restore
import test_corpus


class PublicCorpusTests(unittest.TestCase):
    setUp = test_corpus.CorpusTests.setUp
    source = test_corpus.CorpusTests.source
    def catalog(self) -> tuple[Path, bytes]:
        source = self.source(label="typing")
        source.update(capture_kind="public_recording", license="CC0-1.0", source_url="https://example.org/source",
                      downloaded_at="2026-10-25", consent_status="not_applicable", consent_ref=None)
        content = Path(source["path"]).read_bytes()
        path = self.root / "catalog.json"
        path.write_text(json.dumps({"version": 1, "sources": [{"dataset": "regression", "source": source,
                       "media_url": "https://bigsoundbank.com/UPLOAD/mp3/fixture.mp3",
                       "media_sha256": hashlib.sha256(content).hexdigest()}]}))
        return path, content

    def test_restore_hash_pin_and_cache_only_rerun(self) -> None:
        catalog, content = self.catalog()
        with redirect_stdout(io.StringIO()), patch("fetch_public_corpus.download", return_value=content) as download:
            manifest = restore(catalog, "regression", self.root)
            self.assertTrue(manifest.is_file())
            restore(catalog, "regression", self.root)
            self.assertEqual(download.call_count, 1)

    def test_changed_upstream_and_invalid_catalog_fail(self) -> None:
        catalog, _ = self.catalog()
        with patch("fetch_public_corpus.download", return_value=b"changed"), self.assertRaisesRegex(ValueError, "upstream audio changed"):
            restore(catalog, "regression", self.root)
        payload = json.loads(catalog.read_text())
        payload["sources"][0]["media_url"] = "http://unreviewed.example/audio.mp3"
        catalog.write_text(json.dumps(payload))
        with patch("fetch_public_corpus.download") as download, self.assertRaisesRegex(ValueError, "Invalid media URL"):
            restore(catalog, "regression", self.root)
        download.assert_not_called()


if __name__ == "__main__":
    unittest.main()
