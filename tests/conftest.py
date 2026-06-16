"""Pytest setup: force the in-memory store so tests never touch the real SQLite DB.

This runs before any test module imports `jobfinder.web` (and therefore before the
module-level `store = get_store(settings)` resolves the backend from the environment).
"""
import os

os.environ.setdefault("JOBFINDER_STORAGE", "memory")
