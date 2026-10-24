"""Test-only CLI harness. Synthetic vectors never reach production artifacts."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import runpy
import sys
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import embedding_core


class Client:
    def __init__(self, call_log: Path, fail_after: int | None) -> None:
        self.models = self
        self.log = call_log
        self.fail_after = fail_after
        self.calls = 0

    def embed_content(self, **kwargs: object) -> SimpleNamespace:
        if self.fail_after is not None and self.calls >= self.fail_after:
            raise ValueError("Simulated interruption")
        self.calls += 1
        wav = kwargs["contents"].parts[0].inline_data.data
        with self.log.open("a") as output:
            output.write("request\n")
        seed = int(hashlib.sha256(wav).hexdigest()[:8], 16) % 1000 + 1
        return SimpleNamespace(embeddings=[SimpleNamespace(values=(np.arange(768) + seed).tolist())])

    def close(self) -> None:
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--call-log", required=True, type=Path)
    parser.add_argument("--cache", required=True, type=Path)
    parser.add_argument("--fail-after", type=int)
    parser.add_argument("script", type=Path)
    args, rest = parser.parse_known_args()
    sys.argv = [str(args.script), *rest]
    with patch.object(embedding_core, "new_client", lambda: Client(args.call_log, args.fail_after)), \
            patch.object(embedding_core.RateLimiter, "wait"), \
            patch.object(embedding_core, "CACHE", args.cache):
        runpy.run_path(str(args.script), run_name="__main__")


if __name__ == "__main__":
    main()
