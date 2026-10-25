from pathlib import Path

import pytest

from app.config import load_settings

ENV_KEYS = [
    "GEMINI_API_KEY", "EMBED_MODEL", "DESCRIBE_MODEL", "EMBED_DIM",
    "MAX_DETECT_PER_SEC", "MAX_DESCRIBE_PER_SEC", "DB_PATH", "GEMMA_QUANT", "GEMMA_GPU_MEMORY",
]


def test_defaults_without_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    settings = load_settings(tmp_path / "missing.env")
    assert settings.embed_model == "gemini-embedding-2"
    assert settings.describe_model == "gemini-3.5-flash-lite"
    assert settings.max_detect_per_sec == 1.0
    assert settings.max_describe_per_sec == 0.1


def test_env_file_overrides_defaults(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    env = tmp_path / ".env"
    env.write_text("DESCRIBE_MODEL=gemini-3.1-flash-lite\nMAX_DESCRIBE_PER_SEC=0.5\n")
    settings = load_settings(env)
    assert settings.describe_model == "gemini-3.1-flash-lite"
    assert settings.max_describe_per_sec == 0.5
