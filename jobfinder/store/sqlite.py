"""SQLite-backed store — persists profiles, examples and drafts across restarts.

Stdlib ``sqlite3`` only (no ORM). WAL + busy_timeout + a process-level write lock keep
the single foreground writer and the (future) background scheduler from contending.
Profiles and drafts are stored as JSON blobs and round-tripped through their dataclasses.
``ON CONFLICT ... DO UPDATE`` preserves a row's ``created`` time on update so the outbox
keeps a stable order when a draft is edited.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path

from .base import Store, MAX_PROFILES, MAX_EXAMPLES, MAX_DRAFTS
from ..cv_parser import CVProfile
from ..drafts import ApplicationDraft

_SCHEMA = """
CREATE TABLE IF NOT EXISTS profiles (cv_id TEXT PRIMARY KEY, created REAL NOT NULL, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS examples (id TEXT PRIMARY KEY, created REAL NOT NULL, name TEXT, text TEXT, chars INTEGER);
CREATE TABLE IF NOT EXISTS drafts   (id TEXT PRIMARY KEY, created REAL NOT NULL, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL);
"""
_SCHEMA_VERSION = 1


class SqliteStore(Store):
    def __init__(self, db_path: str | Path) -> None:
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        # check_same_thread=False: FastAPI runs sync endpoints in a threadpool.
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._migrate()

    def _migrate(self) -> None:
        with self._lock, self._conn:
            self._conn.executescript(_SCHEMA)
            row = self._conn.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
            if row is None:
                self._conn.execute("INSERT INTO schema_version(version) VALUES(?)", (_SCHEMA_VERSION,))
            # future forward-only migrations key off row["version"] here.

    def _evict(self, table: str, key: str, cap: int) -> None:
        n = self._conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]
        if n > cap:
            self._conn.execute(
                f"DELETE FROM {table} WHERE {key} IN "
                f"(SELECT {key} FROM {table} ORDER BY created ASC LIMIT ?)",
                (n - cap,),
            )

    # --- profiles ---
    def save_profile(self, cv_id: str, profile: CVProfile) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO profiles(cv_id, created, data) VALUES(?,?,?) "
                "ON CONFLICT(cv_id) DO UPDATE SET data=excluded.data",
                (cv_id, time.time(), json.dumps(profile.to_dict())),
            )
            self._evict("profiles", "cv_id", MAX_PROFILES)

    def get_profile(self, cv_id: str) -> CVProfile | None:
        row = self._conn.execute("SELECT data FROM profiles WHERE cv_id=?", (cv_id,)).fetchone()
        return CVProfile(**json.loads(row["data"])) if row else None

    # --- examples ---
    def save_example(self, example: dict) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO examples(id, created, name, text, chars) VALUES(?,?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET name=excluded.name, text=excluded.text, chars=excluded.chars",
                (example["id"], time.time(), example.get("name"), example.get("text"), example.get("chars")),
            )
            self._evict("examples", "id", MAX_EXAMPLES)

    def list_examples(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, name, text, chars FROM examples ORDER BY created ASC"
        ).fetchall()
        return [dict(r) for r in rows]

    def delete_example(self, example_id: str) -> None:
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM examples WHERE id=?", (example_id,))

    # --- drafts ---
    def save_draft(self, draft: ApplicationDraft) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO drafts(id, created, data) VALUES(?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET data=excluded.data",
                (draft.id, time.time(), json.dumps(draft.to_dict())),
            )
            self._evict("drafts", "id", MAX_DRAFTS)

    def get_draft(self, draft_id: str) -> ApplicationDraft | None:
        row = self._conn.execute("SELECT data FROM drafts WHERE id=?", (draft_id,)).fetchone()
        return ApplicationDraft(**json.loads(row["data"])) if row else None

    def list_drafts(self) -> list[ApplicationDraft]:
        rows = self._conn.execute("SELECT data FROM drafts ORDER BY created ASC").fetchall()
        return [ApplicationDraft(**json.loads(r["data"])) for r in rows]

    def delete_draft(self, draft_id: str) -> None:
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM drafts WHERE id=?", (draft_id,))

    def close(self) -> None:
        self._conn.close()
