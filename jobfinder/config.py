"""Centralized configuration — the single place that reads the environment.

Replaces the scattered ``os.environ.get`` calls across web.py / drafts.py / sources.
Read ``from .config import settings`` everywhere; nothing else should touch os.environ
for app config. Secrets live here and are never persisted to the DB or any response.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _default_data_dir() -> Path:
    """An OS-appropriate per-user data directory for the SQLite store."""
    env = os.environ.get("JOBFINDER_DATA_DIR")
    if env:
        return Path(env)
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "JobFinder"
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg) / "jobfinder"
    return Path.home() / ".local" / "share" / "jobfinder"


@dataclass(frozen=True)
class Settings:
    anthropic_key: str | None
    rapidapi_key: str | None
    model: str
    storage: str                 # "sqlite" | "memory"
    data_dir: Path
    db_path: Path
    default_sources: list[str]
    host: str
    port: int

    @property
    def llm_key_present(self) -> bool:
        return bool(self.anthropic_key)

    @property
    def jsearch_key_present(self) -> bool:
        return bool(self.rapidapi_key)


def load_settings() -> Settings:
    """Build a Settings snapshot from the current environment."""
    data_dir = _default_data_dir()
    storage = os.environ.get("JOBFINDER_STORAGE", "sqlite").strip().lower()
    db_env = os.environ.get("JOBFINDER_DB")
    db_path = Path(db_env) if db_env else data_dir / "jobfinder.db"

    sources_env = os.environ.get("JOBFINDER_DEFAULT_SOURCES")
    if sources_env:
        default_sources = [s.strip() for s in sources_env.split(",") if s.strip()]
    else:
        # Ethics principle: free/official sources on by default, LinkedIn opt-in.
        default_sources = ["remotive", "arbeitnow"]

    return Settings(
        anthropic_key=os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"),
        rapidapi_key=os.environ.get("RAPIDAPI_KEY") or os.environ.get("JSEARCH_API_KEY"),
        model=os.environ.get("JOBFINDER_MODEL", "claude-opus-4-8"),
        storage="memory" if storage == "memory" else "sqlite",
        data_dir=data_dir,
        db_path=db_path,
        default_sources=default_sources,
        host=os.environ.get("JOBFINDER_HOST", "127.0.0.1"),
        port=int(os.environ.get("JOBFINDER_PORT", "8000")),
    )


# Module-level snapshot, resolved once at import. Tests that need a different backend
# set JOBFINDER_STORAGE before importing the app (see tests/conftest.py).
settings = load_settings()
