"""SQLite-backed store — persists profiles, examples and applications across restarts.

Stdlib ``sqlite3`` only (no ORM). A single connection is shared across FastAPI's
threadpool (check_same_thread=False), so a process-level lock serializes EVERY read and
write — a sqlite3 Connection/Cursor is not safe for concurrent use by multiple threads
even under WAL (the corruption is at the Python object level, not the file lock). WAL +
busy_timeout still help the file-level writer/reader story.
Profiles and applications are stored as JSON blobs and round-tripped through their
dataclasses. ``ON CONFLICT ... DO UPDATE`` preserves a row's ``created`` time on update so
the pipeline keeps a stable order when an application is edited.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path

from .base import Store, MAX_PROFILES, MAX_EXAMPLES, MAX_APPLICATIONS
from ..applications import Application
from ..cv_parser import CVProfile

_SCHEMA = """
CREATE TABLE IF NOT EXISTS profiles     (cv_id TEXT PRIMARY KEY, created REAL NOT NULL, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS examples     (id TEXT PRIMARY KEY, created REAL NOT NULL, name TEXT, text TEXT, chars INTEGER);
CREATE TABLE IF NOT EXISTS applications (id TEXT PRIMARY KEY, created REAL NOT NULL, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL);
"""
_SCHEMA_VERSION = 2


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
            if row is None:                      # fresh DB — record the current version
                self._conn.execute("INSERT INTO schema_version(version) VALUES(?)", (_SCHEMA_VERSION,))
                return
            version = row["version"]
            if version < 2:                      # v1.x → v2: carry old drafts into applications
                self._migrate_v1_drafts(self._conn)
                self._conn.execute("UPDATE schema_version SET version=?", (2,))

    @staticmethod
    def _migrate_v1_drafts(conn: sqlite3.Connection) -> None:
        """v1.x stored cover letters in a 'drafts' table. Promote each to an Application
        so the user's outbox isn't silently lost on upgrade, then drop the old table."""
        if conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='drafts'"
        ).fetchone() is None:
            return
        for r in conn.execute("SELECT created, data FROM drafts ORDER BY created ASC").fetchall():
            try:
                d = json.loads(r["data"])
            except Exception:
                continue
            created = r["created"]
            kwargs = dict(
                job_title=d.get("job_title") or "this role",
                company=d.get("company") or "",
                job_url=d.get("job_url") or "",
                job_source=d.get("job_source") or "",
                score=float(d.get("score") or 0),
                status="ready" if d.get("status") == "ready" else "drafting",
                subject=d.get("subject") or "",
                body=d.get("body") or "",
                generator=d.get("generator") or "",
                gen_note=d.get("note") or "",
                created=created, updated=created,
            )
            if d.get("id"):
                kwargs["id"] = d["id"]           # preserve the id (else the factory mints one)
            appn = Application(**kwargs)
            appn.events.append({"ts": created, "type": "migrated", "detail": "Imported from a v1.x draft"})
            conn.execute(
                "INSERT OR IGNORE INTO applications(id, created, data) VALUES(?,?,?)",
                (appn.id, created, json.dumps(appn.to_dict())),
            )
        conn.execute("DROP TABLE drafts")

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
        with self._lock:
            row = self._conn.execute("SELECT data FROM profiles WHERE cv_id=?", (cv_id,)).fetchone()
        return CVProfile.from_dict(json.loads(row["data"])) if row else None

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
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, name, text, chars FROM examples ORDER BY created ASC"
            ).fetchall()
        return [dict(r) for r in rows]

    def delete_example(self, example_id: str) -> None:
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM examples WHERE id=?", (example_id,))

    # --- applications ---
    def save_application(self, app: Application) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO applications(id, created, data) VALUES(?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET data=excluded.data",
                (app.id, time.time(), json.dumps(app.to_dict())),
            )
            self._evict("applications", "id", MAX_APPLICATIONS)

    def get_application(self, app_id: str) -> Application | None:
        with self._lock:
            row = self._conn.execute("SELECT data FROM applications WHERE id=?", (app_id,)).fetchone()
        return Application.from_dict(json.loads(row["data"])) if row else None

    def list_applications(self) -> list[Application]:
        with self._lock:
            rows = self._conn.execute("SELECT data FROM applications ORDER BY created ASC").fetchall()
        return [Application.from_dict(json.loads(r["data"])) for r in rows]

    def delete_application(self, app_id: str) -> None:
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM applications WHERE id=?", (app_id,))

    def close(self) -> None:
        self._conn.close()
