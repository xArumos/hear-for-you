"""Restore pinned public corpus recordings and prepare reproducible manifests."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import urllib.parse
import urllib.request

from corpus import DATASETS, HEX, prepare, require, validate_source
from dataset_io import DATA, atomic_bytes, portable_path, sha256_file, write_json

HOSTS = {"bigsoundbank.com", "cdn.freesound.org", "raw.githubusercontent.com", "www.freesoundslibrary.com"}


def download(url: str) -> bytes:
    parsed = urllib.parse.urlparse(url)
    require(parsed.scheme == "https" and parsed.hostname in HOSTS, "Use the catalog's verified public HTTPS media hosts.")
    with urllib.request.urlopen(url, timeout=30) as response:
        require(urllib.parse.urlparse(response.url).hostname in HOSTS, "Unexpected download redirect.")
        content = response.read(100_000_001)
    require(0 < len(content) <= 100_000_000, "Public recording must be at most 100 MB.")
    return content


def restore(catalog: Path, dataset: str, output_dir: Path = DATA) -> Path:
    payload = json.loads(catalog.read_text())
    require(payload.get("version") == 1, "Unsupported source catalog version.")
    entries = [entry for entry in payload["sources"] if entry["dataset"] == dataset]
    require(entries, f"No sources for {dataset}.")
    sources = []
    # Validate every catalog entry before downloading any audio.
    for entry in entries:
        source = dict(entry["source"])
        validate_source(source, dataset)
        require(source["capture_kind"] == "public_recording", "The public downloader accepts only public recordings.")
        require(bool(HEX.fullmatch(entry["media_sha256"])), "Each public download needs a pinned SHA-256.")
        parsed = urllib.parse.urlparse(entry["media_url"])
        require(parsed.scheme == "https" and parsed.hostname in HOSTS, "Invalid media URL.")
        source["path"] = portable_path(output_dir / "raw/public/corpus" / f"{source['clip_id']}.mp3")
        sources.append(source)
    for entry, source in zip(entries, sources, strict=True):
        path = output_dir / "raw/public/corpus" / f"{source['clip_id']}.mp3"
        if not path.is_file() or sha256_file(path) != entry["media_sha256"]:
            content = download(entry["media_url"])
            require(hashlib.sha256(content).hexdigest() == entry["media_sha256"], f"{source['clip_id']}: upstream audio changed; review before updating the catalog.")
            atomic_bytes(path, content)
        print(f"source={source['clip_id']} status=verified", flush=True)
    inputs = output_dir / f"raw/public/{dataset}_sources.json"
    write_json(inputs, {"version": 1, "sources": sources})
    manifest = prepare(inputs, dataset, output_dir)
    published = output_dir / "manifests" / f"{dataset}.csv"
    if published.is_file():
        for name in (f"{dataset}.csv", f"{dataset}_metadata.json", f"{dataset}_quality.json"):
            reference = published.with_name(name)
            require(reference.is_file() and reference.read_bytes() == manifest.with_name(name).read_bytes(),
                    f"{dataset}: restored conversion differs from the published bundle; inspect catalog/decoder versions before re-embedding.")
    print(f"Prepared manifest: {manifest}")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=DATA / "public_corpus_sources.json")
    parser.add_argument("--dataset", choices=[*DATASETS, "all"], default="all")
    parser.add_argument("--output-dir", type=Path, default=DATA)
    args = parser.parse_args()
    try:
        for dataset in DATASETS if args.dataset == "all" else [args.dataset]:
            restore(args.catalog, dataset, args.output_dir.resolve())
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(1, f"Public corpus restoration stopped: {exc}\n")


if __name__ == "__main__":
    main()
