"""Pluggable persistence: a Store interface with memory and SQLite backends."""
from __future__ import annotations

from .base import Store, MAX_PROFILES, MAX_EXAMPLES, MAX_APPLICATIONS
from .memory import MemoryStore


def get_store(settings) -> Store:
    """Build the store chosen by settings ('sqlite' default, 'memory' for tests/ephemeral)."""
    if settings.storage == "memory":
        return MemoryStore()
    from .sqlite import SqliteStore
    return SqliteStore(settings.db_path)


__all__ = ["Store", "MemoryStore", "get_store", "MAX_PROFILES", "MAX_EXAMPLES", "MAX_APPLICATIONS"]
