"""Shared manifest and atomic artifact I/O for offline data tools."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile

DATA = Path(__file__).resolve().parent
ROOT = DATA.parent
FIELDS = ["clip_id", "path", "label", "source", "fold", "recorded_at", "device"]


def atomic_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def write_json(path: Path, value: object) -> None:
    atomic_bytes(path, (json.dumps(value, indent=2, sort_keys=True) + "\n").encode())


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def manifest_bytes(rows: list[dict[str, str]]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != FIELDS:
            raise ValueError(f"{path.name}: columns must be {','.join(FIELDS)}.")
        rows = list(reader)
    if not rows:
        raise ValueError(f"{path.name}: no recordings; add rows before running this tool.")
    if any(set(row) != set(FIELDS) or any(value is None for value in row.values()) for row in rows):
        raise ValueError(f"{path.name}: malformed CSV row.")
    return rows


def portable_path(path: Path) -> str:
    resolved = path.resolve()
    return resolved.relative_to(ROOT).as_posix() if resolved.is_relative_to(ROOT) else str(resolved)
