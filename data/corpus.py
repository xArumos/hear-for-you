"""Provenance-aware preparation for smoke alarms and held-out regression audio."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, timedelta
import hashlib
import json
import math
from pathlib import Path
import re
import tempfile
import wave

import numpy as np

from convert import CORPUS_PREPROCESS_VERSION, RATE, SAMPLES, loudest_start, write_pcm_wav
from dataset_io import DATA, ROOT, atomic_bytes, manifest_bytes, portable_path, read_csv, sha256_file, write_json
from prepare_recordings import decode_pcm, timestamp

DATASETS = ("smoke_alarm", "regression")
PREPARATION_VERSION = CORPUS_PREPROCESS_VERSION
BUILTINS = {"builtin_smoke_alarm", "builtin_dog_bark", "builtin_crying_baby",
            "builtin_door_knock", "builtin_glass_breaking", "builtin_siren"}
NEGATIVES = {"typing", "desk_tapping", "footsteps", "speech", "television_music", "fan_ac"}
PRIORITIES = ("builtin_door_knock", "typing", "desk_tapping", "footsteps", "speech")
KINDS = {"direct_capture", "speaker_playback", "public_recording", "simulation"}
LICENSES = {"CC0-1.0", "CC-BY-3.0", "CC-BY-4.0", "consented-private"}
HEX = re.compile(r"[0-9a-f]{64}")


def require(condition: object, message: str) -> None:
    if not condition:
        raise ValueError(message)


def number(value: object, minimum: float = 0) -> bool:
    return (type(value) in (int, float) and math.isfinite(value) and value >= minimum)


def validate_source(source: dict[str, object], dataset: str) -> None:
    """Validate evidence fields; null means unknown, never inferred metadata."""
    required = {"clip_id", "path", "label", "source_group", "capture_kind", "license",
                "source_url", "author", "attribution", "downloaded_at", "consent_status",
                "consent_ref", "recorded_at", "device", "room", "distance_m", "position",
                "door_position", "background", "event_variation", "alarm_pattern", "tone_hz",
                "windowing", "events", "lineage"}
    require(required <= source.keys(), f"Missing source fields: {sorted(required - source.keys())}")
    require(isinstance(source["clip_id"], str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", source["clip_id"]), "Invalid clip_id.")
    for field in ("path", "source_group", "author", "attribution", "event_variation"):
        require(isinstance(source[field], str) and bool(source[field].strip()), f"Provide {field}.")
    require(source["capture_kind"] in KINDS, "Invalid capture_kind.")
    require(source["license"] in LICENSES, "Use verified CC0/CC BY or documented private consent.")
    require(source["consent_status"] in {"granted", "not_applicable"}, "Consent must be resolved before preparation.")
    if source["license"] == "consented-private":
        require(source["consent_status"] == "granted" and isinstance(source["consent_ref"], str)
                and bool(source["consent_ref"].strip()), "Private recordings need granted consent and a non-sensitive reference.")
    else:
        require(isinstance(source["source_url"], str) and source["source_url"].startswith("https://"), "Licensed audio needs its source page URL.")
        try:
            date.fromisoformat(str(source["downloaded_at"]))
        except ValueError:
            raise ValueError("Licensed audio needs an actual ISO download date.") from None
    for field in ("recorded_at", "device", "room", "position", "door_position", "background"):
        require(source[field] is None or (isinstance(source[field], str) and bool(source[field].strip())), f"{field}: use a value or null for unknown.")
    if source["recorded_at"] is not None:
        timestamp(str(source["recorded_at"]))
    require(source["distance_m"] is None or number(source["distance_m"]), "distance_m must be nonnegative or null.")
    require(source["position"] in {None, "near", "across_room", "another_room"}, "Invalid position.")
    require(source["alarm_pattern"] in {None, "T3", "T4", "continuous", "unknown"}, "Invalid alarm_pattern.")
    require(source["tone_hz"] is None or number(source["tone_hz"], 1), "tone_hz must be positive or null.")
    require(source["windowing"] in {"isolated", "continuous", "sustained"}, "Invalid windowing.")
    require(source.get("max_windows") is None or (type(source["max_windows"]) is int and source["max_windows"] > 0), "max_windows must be a positive integer or null.")
    require(source.get("window_selection", "chronological") in {"chronological", "highest_energy"}, "Invalid window selection.")
    require(dataset == "smoke_alarm" or source.get("window_selection", "chronological") == "chronological", "Regression timing must remain chronological.")
    for optional in ("alarm_model",):
        require(source.get(optional) is None or (isinstance(source[optional], str) and source[optional].strip()), f"{optional}: use a value or null.")
    require(source.get("reverberant") is None or type(source["reverberant"]) is bool, "reverberant must be boolean or null.")
    require(isinstance(source["lineage"], list) and all(isinstance(v, str) and v.strip() for v in source["lineage"]), "lineage must list source-group IDs for every playback/mix ancestor.")
    if source["capture_kind"] in {"speaker_playback", "simulation"}:
        require(bool(source["lineage"]), "Playback and simulations require source lineage.")
    label = source["label"]
    if dataset == "smoke_alarm":
        require(label in {"builtin_smoke_alarm", "other", "co_alarm"}, "Invalid smoke-alarm dataset label.")
        if label == "builtin_smoke_alarm":
            require(source["alarm_pattern"] != "T4", "CO/T4 must not be labeled smoke alarm.")
        if label == "co_alarm":
            require(source["alarm_pattern"] == "T4", "CO examples must explicitly identify T4.")
        require(source["capture_kind"] != "simulation", "Synthetic examples cannot enter the smoke training corpus.")
    else:
        require(label in BUILTINS | NEGATIVES | {"other", "co_alarm"}, "Invalid regression label.")
    require(isinstance(source["events"], list), "events must be a list of annotated events.")
    previous = -1.0
    for event in source["events"]:
        require(isinstance(event, dict) and {"at_seconds", "sound_id", "expected_alert"} <= event.keys(), "Incomplete event annotation.")
        require(number(event["at_seconds"]) and event["at_seconds"] >= previous, "Event times must be ordered and nonnegative.")
        require(type(event["expected_alert"]) is bool, "expected_alert must be boolean.")
        require(event["sound_id"] is None or event["sound_id"] in BUILTINS, "Use a built-in sound ID or null for an unknown event.")
        if "end_seconds" in event:
            require(number(event["end_seconds"]) and event["end_seconds"] > event["at_seconds"], "Event end must follow its onset.")
        if dataset == "smoke_alarm" and label == "builtin_smoke_alarm" and source["windowing"] != "isolated":
            require("end_seconds" in event, "Sustained training alarms need annotated event ends to exclude baseline-only windows.")
        previous = event["at_seconds"]
    if label in BUILTINS:
        require(bool(source["events"]), "Target recordings require event timing annotations.")


def grouped_sources(sources: list[dict[str, object]]) -> dict[str, str]:
    """Union aliases, exact duplicates and declared ancestors before assigning folds."""
    parents: dict[str, str] = {}

    def root(key: str) -> str:
        parents.setdefault(key, key)
        while parents[key] != key:
            parents[key] = parents[parents[key]]
            key = parents[key]
        return key

    for source in sources:
        keys = ["group:" + str(source["source_group"]), "sha256:" + str(source["source_sha256"])]
        keys.extend("group:" + str(v) for v in source["lineage"])
        for key in keys[1:]:
            a, b = sorted((root(keys[0]), root(key)))
            parents[b] = a
    return {str(s["clip_id"]): root("group:" + str(s["source_group"])) for s in sources}


def assign_folds(sources: list[dict[str, object]], dataset: str) -> dict[str, str]:
    if dataset == "regression":
        return {str(s["clip_id"]): "" for s in sources}
    groups = grouped_sources(sources)
    members: dict[str, list[dict[str, object]]] = defaultdict(list)
    for source in sources:
        members[groups[str(source["clip_id"])]].append(source)
    counts = {str(f): Counter() for f in range(1, 6)}
    result = {}
    for group, items in sorted(members.items(), key=lambda item: hashlib.sha256(item[0].encode()).hexdigest()):
        # A group containing a CO example is evaluation-only in its entirety.
        fold = "" if any(s["label"] == "co_alarm" for s in items) else min(
            counts, key=lambda f: (sum(counts[f][str(s["label"])] for s in items), sum(counts[f].values()), f))
        for source in items:
            result[str(source["clip_id"])] = fold
            if fold:
                counts[fold][str(source["label"])] += 1
    return result


def coverage(sources: list[dict[str, object]], dataset: str) -> dict[str, object]:
    groups = grouped_sources(sources)
    counts = Counter(str(s["label"]) for s in sources)
    deficits = {}
    if dataset == "smoke_alarm":
        for label, target in (("builtin_smoke_alarm", 30), ("other", 10)):
            examples = sum(int(s.get("accepted_windows", 0)) for s in sources if s["label"] == label)
            independent = len({groups[str(s["clip_id"])] for s in sources if s["label"] == label})
            deficits[label] = max(0, target - examples)
            deficits[f"{label}_fold_groups"] = max(0, 5 - independent)
        deficits["T3_coverage"] = int(not any(s["label"] == "builtin_smoke_alarm" and s["alarm_pattern"] == "T3" for s in sources))
        deficits["low_frequency_coverage"] = int(not any(s["label"] == "builtin_smoke_alarm" and s["tone_hz"] is not None and 440 <= s["tone_hz"] <= 620 for s in sources))
        deficits["CO_T4_evaluation"] = int(not any(s["label"] == "co_alarm" for s in sources))
        alarms = [s for s in sources if s["label"] == "builtin_smoke_alarm"]
        deficits["alarm_models"] = max(0, 2 - len({s["alarm_model"] for s in alarms if s.get("alarm_model")}))
        deficits["alarm_rooms"] = max(0, 2 - len({s["room"] for s in alarms if s["room"]}))
    else:
        devices = Counter(str(s["device"]) for s in sources if s["capture_kind"] == "direct_capture" and s["device"])
        primary_device = min(devices, key=lambda device: (-devices[device], device)) if devices else None
        for label in PRIORITIES:
            for position in ("near", "across_room", "another_room"):
                qualifying = {groups[str(s["clip_id"])] for s in sources
                              if s["label"] == label and s["position"] == position
                              and s["capture_kind"] == "direct_capture"
                              and s["device"] == primary_device
                              and all(s[k] is not None for k in ("device", "room", "distance_m", "background", "door_position"))}
                deficits[f"{label}/{position}"] = max(0, 5 - len(qualifying))
        for label in sorted((BUILTINS | NEGATIVES) - set(PRIORITIES)):
            deficits[f"extended/{label}"] = max(0, 5 - len({groups[str(s["clip_id"])] for s in sources if s["label"] == label and s["capture_kind"] != "simulation"}))
        for condition in ("reverberant", "sustained"):
            deficits[f"extended/{condition}"] = max(0, 5 - len({groups[str(s["clip_id"])] for s in sources if
                (s["windowing"] == "sustained" if condition == "sustained" else s.get("reverberant") is True)}))
    return {"source_counts": dict(counts), "independent_groups": len(set(groups.values())),
            "primary_device": primary_device if dataset == "regression" else None,
            "capture_kinds": dict(Counter(str(s["capture_kind"]) for s in sources)),
            "target_deficits": deficits, "collection_target_met": not any(deficits.values()),
            "reliability_established": False}


def prepare(input_path: Path, dataset: str, output_dir: Path = DATA) -> Path:
    require(dataset in DATASETS, "Unknown corpus dataset.")
    payload = json.loads(input_path.read_text())
    require(isinstance(payload, dict) and payload.get("version") == 1 and isinstance(payload.get("sources"), list) and payload["sources"], "Supply version=1 and nonempty sources.")
    sources = payload["sources"]
    seen = set()
    raw = (output_dir / "raw").resolve()
    for source in sources:
        require(isinstance(source, dict), "Each source must be an object.")
        validate_source(source, dataset)
        require(source["clip_id"] not in seen, "Duplicate source clip_id.")
        seen.add(source["clip_id"])
        path = (ROOT / str(source["path"])).resolve()
        require(path.is_relative_to(raw) and path.is_file(), "All originals must exist under output-dir/raw.")
        source["path"] = portable_path(path)
        source["source_sha256"] = sha256_file(path)
    folds = assign_folds(sources, dataset)
    generation = hashlib.sha256(json.dumps({"sources": sources, "preparation": PREPARATION_VERSION}, sort_keys=True).encode()).hexdigest()[:20]
    directory = output_dir / "raw/prepared" / dataset / generation
    directory.mkdir(parents=True, exist_ok=True)
    rows, clips = [], {}
    for source in sorted(sources, key=lambda s: s["clip_id"]):
        identifier = str(source["clip_id"])
        with tempfile.TemporaryDirectory(dir=directory) as temporary:
            decoded = Path(temporary) / "audio.pcm"
            decode_pcm(ROOT / str(source["path"]), decoded)
            samples = np.fromfile(decoded, dtype="<i2")
        require(len(samples) >= SAMPLES and bool(np.any(samples)), f"{identifier}: need at least three seconds of non-silent audio.")
        require(all(e["at_seconds"] < len(samples) / RATE and e.get("end_seconds", e["at_seconds"]) <= len(samples) / RATE for e in source["events"]), "Annotation lies outside source duration.")
        # Full normalized audio is for chronological microphone replay, never for upload as a clip.
        replay = directory / f"{identifier}_replay.wav"
        with wave.open(str(replay), "wb") as stream:
            stream.setparams((1, 2, RATE, len(samples), "NONE", "not compressed"))
            stream.writeframes(samples.tobytes())
        source.update({"replay_path": portable_path(replay), "replay_sha256": sha256_file(replay),
                       "duration_seconds": len(samples) / RATE})
        offsets = [loudest_start(samples)] if source["windowing"] == "isolated" else list(range(0, len(samples) - SAMPLES + 1, SAMPLES))
        if source.get("window_selection") == "highest_energy":
            offsets = sorted(offsets, key=lambda offset: (-float(np.mean(samples[offset:offset + SAMPLES].astype(np.float64) ** 2)), offset))
        exclusions = []
        annotation_exclusions = []
        before = len(rows)
        for index, offset in enumerate(offsets):
            if source.get("max_windows") and len(rows) - before >= source["max_windows"]:
                break
            pcm = samples[offset:offset + SAMPLES]
            if not np.any(pcm):
                exclusions.append(offset)
                continue
            if dataset == "smoke_alarm" and source["label"] == "builtin_smoke_alarm":
                matching = [event for event in source["events"] if event["sound_id"] == "builtin_smoke_alarm"
                            and event["at_seconds"] < (offset + SAMPLES) / RATE
                            and event.get("end_seconds", event["at_seconds"] + 1 / RATE) > offset / RATE]
                if not matching:
                    annotation_exclusions.append(offset)
                    continue
            clip_id = f"{identifier}__{index:06d}"
            target = directory / f"{clip_id}.wav"
            write_pcm_wav(target, pcm.tobytes())
            recorded_at = (timestamp(str(source["recorded_at"])) + timedelta(seconds=offset / RATE)).isoformat().replace("+00:00", "Z") if source["recorded_at"] else ""
            rows.append({"clip_id": clip_id, "path": portable_path(target), "label": str(source["label"]),
                         "source": str(source["capture_kind"]), "fold": folds[identifier],
                         "recorded_at": recorded_at, "device": str(source["device"] or "")})
            clips[clip_id] = {"parent_clip_id": identifier, "source_sha256": source["source_sha256"],
                              "offset_samples": offset, "duration_seconds": 3,
                              "audio_sha256": sha256_file(target), "windowing": source["windowing"]}
        source["silent_excluded_seconds"] = len(exclusions) * 3
        source["annotation_excluded_seconds"] = len(annotation_exclusions) * 3
        require(len(rows) > before, f"{identifier}: no usable annotated windows; review event timing and source length.")
        source["accepted_windows"] = len(rows) - before
        source["trailing_seconds"] = 0 if source["windowing"] == "isolated" else (len(samples) % SAMPLES) / RATE
        require(sha256_file(ROOT / str(source["path"])) == source["source_sha256"], "Original changed during preparation.")
    require(rows, "No usable windows; previous artifacts preserved.")
    rows.sort(key=lambda r: r["clip_id"])
    encoded = manifest_bytes(rows)
    metadata = {"version": 1, "dataset": dataset, "role": "training_and_test" if dataset == "smoke_alarm" else "held_out_regression",
                "generation": generation, "preparation": PREPARATION_VERSION, "manifest_sha256": hashlib.sha256(encoded).hexdigest(),
                "sources": {str(s["clip_id"]): s for s in sources}, "clips": clips}
    write_json(directory / f"{dataset}_metadata.json", metadata)
    write_json(directory / f"{dataset}_quality.json", coverage(sources, dataset))
    manifest = directory / f"{dataset}.csv"
    atomic_bytes(manifest, encoded)
    return manifest


def read_prepared(manifest: Path, dataset: str) -> tuple[list[dict[str, str]], list[Path]]:
    rows = read_csv(manifest)
    metadata_path = manifest.with_name(f"{dataset}_metadata.json")
    quality_path = manifest.with_name(f"{dataset}_quality.json")
    metadata = json.loads(metadata_path.read_text())
    require(metadata.get("version") == 1 and metadata.get("dataset") == dataset
            and metadata.get("preparation") == PREPARATION_VERSION
            and metadata.get("role") == ("training_and_test" if dataset == "smoke_alarm" else "held_out_regression")
            and metadata.get("manifest_sha256") == sha256_file(manifest), "Stale corpus provenance.")
    sources = list(metadata["sources"].values())
    require(set(metadata["sources"]) == {s["clip_id"] for s in sources}, "Source IDs do not match provenance keys.")
    for source in sources:
        validate_source(source, dataset)
        require(bool(HEX.fullmatch(source["source_sha256"])), "Invalid source hash.")
        for path_key, hash_key in (("path", "source_sha256"), ("replay_path", "replay_sha256")):
            path = ROOT / source[path_key]
            require(not path.is_file() or sha256_file(path) == source[hash_key], f"{path_key} differs from corpus provenance.")
    folds = assign_folds(sources, dataset)
    identifiers = [r["clip_id"] for r in rows]
    require(identifiers == sorted(set(identifiers)) and set(identifiers) == set(metadata["clips"]), "Manifest/clip metadata mismatch.")
    accepted = Counter(c["parent_clip_id"] for c in metadata["clips"].values())
    require(all(s.get("accepted_windows") == accepted[s["clip_id"]] for s in sources), "Accepted-window counts disagree with clip provenance.")
    for row in rows:
        clip = metadata["clips"][row["clip_id"]]
        source = metadata["sources"][clip["parent_clip_id"]]
        require(type(clip["offset_samples"]) is int and clip["offset_samples"] >= 0
                and clip["offset_samples"] + SAMPLES <= round(source["duration_seconds"] * RATE)
                and clip["duration_seconds"] == 3 and clip["windowing"] == source["windowing"], "Invalid clip timing provenance.")
        require(row["fold"] == folds[clip["parent_clip_id"]] and row["label"] == source["label"]
                and row["source"] == source["capture_kind"] and clip["source_sha256"] == source["source_sha256"], "Label, source or fold mismatch.")
        path = ROOT / row["path"]
        require(not path.is_file() or sha256_file(path) == clip["audio_sha256"], "Converted audio changed.")
    require(json.loads(quality_path.read_text()) == coverage(sources, dataset), "Collection report is stale.")
    return rows, [metadata_path, quality_path]


def overlap(manifest: Path, dataset: str, output_dir: Path = DATA) -> dict[str, object]:
    """Compare source identities, not just filenames, against training provenance."""
    metadata = json.loads(manifest.with_name(f"{dataset}_metadata.json").read_text())
    training_hashes, training_groups = set(), set()
    if dataset == "regression":
        other = output_dir / "manifests/smoke_alarm_metadata.json"
        if other.is_file():
            for s in json.loads(other.read_text())["sources"].values():
                training_hashes.add(s["source_sha256"])
                training_groups.update([s["source_group"], *s["lineage"]])
        # ESC-50 originals and conversion hashes are available in its public manifest/checkpoints.
        esc = output_dir / "manifests/esc50.csv"
        if esc.is_file():
            for row in read_csv(esc):
                training_groups.update([row["clip_id"], f"esc50:{row['clip_id']}"])
                for path in (ROOT / row["path"], output_dir / "raw/esc50/audio" / f"{row['clip_id']}.wav"):
                    if path.is_file():
                        training_hashes.add(sha256_file(path))
    shared = [identifier for identifier, s in metadata["sources"].items()
              if s["source_sha256"] in training_hashes or training_groups.intersection([s["source_group"], *s["lineage"]])]
    simulated = [identifier for identifier, s in metadata["sources"].items() if s["capture_kind"] == "simulation"]
    return {"shared_sources": sorted(shared), "simulated_sources": sorted(simulated),
            "held_out_eligible": dataset == "regression" and not shared and not simulated,
            "limitation": "Declared lineage and available hashes detect overlap; unknown upstream reuse cannot be ruled out."}
