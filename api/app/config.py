"""Settings read from api/.env, with real environment variables taking precedence."""

import os
from dataclasses import dataclass
from pathlib import Path

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def _read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


@dataclass(frozen=True)
class Settings:
    gemini_api_key: str
    embed_model: str
    describe_model: str
    embed_dim: int
    max_detect_per_sec: float
    max_describe_per_sec: float
    db_path: str


def load_settings(path: Path = ENV_PATH) -> Settings:
    env = {**_read_env_file(path), **os.environ}
    return Settings(
        gemini_api_key=env.get("GEMINI_API_KEY", ""),
        embed_model=env.get("EMBED_MODEL", "gemini-embedding-2"),
        describe_model=env.get("DESCRIBE_MODEL", "gemini-3.5-flash-lite"),
        embed_dim=int(env.get("EMBED_DIM", "768")),
        max_detect_per_sec=float(env.get("MAX_DETECT_PER_SEC", "1")),
        max_describe_per_sec=float(env.get("MAX_DESCRIBE_PER_SEC", "0.1")),
        db_path=env.get("DB_PATH", "./hearalert.db"),
    )


settings = load_settings()
