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

from .base import (Store, MAX_PROFILES, MAX_EXAMPLES, MAX_APPLICATIONS, MAX_SAVED_SEARCHES,
                   MAX_NOTIFICATIONS, MAX_CONSULTANTS, MAX_OPPORTUNITIES, MAX_CLIENTS)
from ..applications import Application
from ..clients import Client
from ..consultants import Consultant
from ..cv_parser import CVProfile
from ..house import House, HOUSE_ID
from ..notifications import Notification
from ..opportunities import Opportunity
from ..saved_searches import SavedSearch

_SCHEMA = """
CREATE TABLE IF NOT EXISTS profiles      (cv_id TEXT PRIMARY KEY, created REAL NOT NULL, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS examples      (id TEXT PRIMARY KEY, created REAL NOT NULL, name TEXT, text TEXT, chars INTEGER);
CREATE TABLE IF NOT EXISTS applications  (id TEXT PRIMARY KEY, created REAL NOT NULL, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS saved_searches(id TEXT PRIMARY KEY, created REAL NOT NULL, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS notifications (id TEXT PRIMARY KEY, created REAL NOT NULL, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS consultants   (id TEXT PRIMARY KEY, created REAL NOT NULL, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS house         (id TEXT PRIMARY KEY, created REAL NOT NULL, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS opportunities (id TEXT PRIMARY KEY, created REAL NOT NULL, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS clients       (id TEXT PRIMARY KEY, created REAL NOT NULL, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL);
"""
_SCHEMA_VERSION = 7


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
            self._conn.executescript(_SCHEMA)    # idempotent schema — also creates any new tables
            row = self._conn.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
            if row is None:                      # fresh DB — record the current version
                self._conn.execute("INSERT INTO schema_version(version) VALUES(?)", (_SCHEMA_VERSION,))
                return
            version = row["version"]
            # Ordered DATA-backfill steps, keyed by the version they upgrade TO. The schema
            # itself (CREATE TABLE IF NOT EXISTS above) is applied every open, so a version
            # that only ADDS empty tables (v3 saved_searches, v4 notifications, v5
            # consultants/house) needs NO step here. A step runs only when the stored version
            # is below its target, so a future data backfill can't be skipped by a later bump.
            steps = [(2, self._migrate_v1_drafts)]   # v1.x → v2: carry old drafts into applications
            for to_version, step in steps:
                if version < to_version:
                    step(self._conn)
            if version < _SCHEMA_VERSION:
                self._conn.execute("UPDATE schema_version SET version=?", (_SCHEMA_VERSION,))

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

    # --- saved searches ---
    def save_saved_search(self, search: SavedSearch) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO saved_searches(id, created, data) VALUES(?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET data=excluded.data",
                (search.id, time.time(), json.dumps(search.to_dict())),
            )
            self._evict("saved_searches", "id", MAX_SAVED_SEARCHES)

    def get_saved_search(self, search_id: str) -> SavedSearch | None:
        with self._lock:
            row = self._conn.execute("SELECT data FROM saved_searches WHERE id=?", (search_id,)).fetchone()
        return SavedSearch.from_dict(json.loads(row["data"])) if row else None

    def list_saved_searches(self) -> list[SavedSearch]:
        with self._lock:
            rows = self._conn.execute("SELECT data FROM saved_searches ORDER BY created ASC").fetchall()
        return [SavedSearch.from_dict(json.loads(r["data"])) for r in rows]

    def update_saved_search(self, search_id, mutator):
        """Atomic read-modify-write under a single lock acquisition, so a background
        alert sweep and a concurrent /run or /seen request can't clobber each other's
        seen_ids / new_count (lost-update race). Returns the updated row, or None."""
        with self._lock, self._conn:
            row = self._conn.execute("SELECT data FROM saved_searches WHERE id=?", (search_id,)).fetchone()
            if row is None:
                return None
            s = SavedSearch.from_dict(json.loads(row["data"]))
            mutator(s)
            self._conn.execute(
                "INSERT INTO saved_searches(id, created, data) VALUES(?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET data=excluded.data",
                (s.id, time.time(), json.dumps(s.to_dict())),
            )
        return s

    def delete_saved_search(self, search_id: str) -> None:
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM saved_searches WHERE id=?", (search_id,))

    # --- consultants (the bench) ---
    def save_consultant(self, consultant: Consultant) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO consultants(id, created, data) VALUES(?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET data=excluded.data",
                (consultant.id, time.time(), json.dumps(consultant.to_dict())),
            )
            self._evict("consultants", "id", MAX_CONSULTANTS)

    def get_consultant(self, consultant_id: str) -> Consultant | None:
        with self._lock:
            row = self._conn.execute("SELECT data FROM consultants WHERE id=?", (consultant_id,)).fetchone()
        return Consultant.from_dict(json.loads(row["data"])) if row else None

    def list_consultants(self) -> list[Consultant]:
        with self._lock:
            rows = self._conn.execute("SELECT data FROM consultants ORDER BY created ASC").fetchall()
        return [Consultant.from_dict(json.loads(r["data"])) for r in rows]

    def delete_consultant(self, consultant_id: str) -> None:
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM consultants WHERE id=?", (consultant_id,))

    # --- house (single-row identity) ---
    def get_house(self) -> House | None:
        with self._lock:
            row = self._conn.execute("SELECT data FROM house WHERE id=?", (HOUSE_ID,)).fetchone()
        return House.from_dict(json.loads(row["data"])) if row else None

    def save_house(self, house: House) -> None:
        house.id = HOUSE_ID                       # enforce the single-row invariant
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO house(id, created, data) VALUES(?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET data=excluded.data",
                (HOUSE_ID, time.time(), json.dumps(house.to_dict())),
            )

    # --- opportunities (pursued projects + proposal audit trail) ---
    def save_opportunity(self, opp: Opportunity) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO opportunities(id, created, data) VALUES(?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET data=excluded.data",
                (opp.id, time.time(), json.dumps(opp.to_dict())),
            )
            self._evict("opportunities", "id", MAX_OPPORTUNITIES)

    def get_opportunity(self, opp_id: str) -> Opportunity | None:
        with self._lock:
            row = self._conn.execute("SELECT data FROM opportunities WHERE id=?", (opp_id,)).fetchone()
        return Opportunity.from_dict(json.loads(row["data"])) if row else None

    def list_opportunities(self) -> list[Opportunity]:
        with self._lock:
            rows = self._conn.execute("SELECT data FROM opportunities ORDER BY created ASC").fetchall()
        return [Opportunity.from_dict(json.loads(r["data"])) for r in rows]

    def delete_opportunity(self, opp_id: str) -> None:
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM opportunities WHERE id=?", (opp_id,))

    def get_opportunity_by_posting(self, source: str, source_uid: str) -> Opportunity | None:
        if not source_uid:
            return None
        with self._lock:
            rows = self._conn.execute("SELECT data FROM opportunities ORDER BY created ASC").fetchall()
        for r in rows:                            # small table; linear scan over the JSON blobs
            d = json.loads(r["data"])
            if d.get("source") == source and d.get("source_uid") == source_uid:
                return Opportunity.from_dict(d)
        return None

    def update_opportunity(self, opp_id: str, mutator):
        with self._lock, self._conn:
            row = self._conn.execute("SELECT data FROM opportunities WHERE id=?", (opp_id,)).fetchone()
            if row is None:
                return None
            opp = Opportunity.from_dict(json.loads(row["data"]))
            mutator(opp)
            self._conn.execute(
                "INSERT INTO opportunities(id, created, data) VALUES(?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET data=excluded.data",
                (opp.id, time.time(), json.dumps(opp.to_dict())),
            )
        return opp

    # --- clients (direct-warm relationship layer) ---
    def save_client(self, client: Client) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO clients(id, created, data) VALUES(?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET data=excluded.data",
                (client.id, time.time(), json.dumps(client.to_dict())),
            )
            self._evict("clients", "id", MAX_CLIENTS)

    def get_client(self, client_id: str) -> Client | None:
        with self._lock:
            row = self._conn.execute("SELECT data FROM clients WHERE id=?", (client_id,)).fetchone()
        return Client.from_dict(json.loads(row["data"])) if row else None

    def list_clients(self) -> list[Client]:
        with self._lock:
            rows = self._conn.execute("SELECT data FROM clients ORDER BY created ASC").fetchall()
        return [Client.from_dict(json.loads(r["data"])) for r in rows]

    def delete_client(self, client_id: str) -> None:
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM clients WHERE id=?", (client_id,))

    # --- data rights ---
    def export_all(self) -> dict:
        with self._lock:
            prof = self._conn.execute("SELECT cv_id, data FROM profiles").fetchall()
            ex = self._conn.execute("SELECT id, name, text, chars FROM examples ORDER BY created ASC").fetchall()
            apps = self._conn.execute("SELECT data FROM applications ORDER BY created ASC").fetchall()
            ss = self._conn.execute("SELECT data FROM saved_searches ORDER BY created ASC").fetchall()
            notes = self._conn.execute("SELECT data FROM notifications ORDER BY created DESC").fetchall()
            cons = self._conn.execute("SELECT data FROM consultants ORDER BY created ASC").fetchall()
            house = self._conn.execute("SELECT data FROM house WHERE id=?", (HOUSE_ID,)).fetchone()
            opps = self._conn.execute("SELECT data FROM opportunities ORDER BY created ASC").fetchall()
            clients = self._conn.execute("SELECT data FROM clients ORDER BY created ASC").fetchall()
        return {
            "profiles": {r["cv_id"]: json.loads(r["data"]) for r in prof},
            "examples": [dict(r) for r in ex],
            "applications": [json.loads(r["data"]) for r in apps],
            "saved_searches": [json.loads(r["data"]) for r in ss],
            "notifications": [json.loads(r["data"]) for r in notes],
            "consultants": [json.loads(r["data"]) for r in cons],
            "house": json.loads(house["data"]) if house else {},
            "opportunities": [json.loads(r["data"]) for r in opps],
            "clients": [json.loads(r["data"]) for r in clients],
        }

    def delete_all(self) -> None:
        # one lock acquisition across DELETE + commit + VACUUM, so no other thread can INSERT in
        # a gap. VACUUM can't run inside a transaction, so commit() explicitly first, then VACUUM
        # runs in autocommit — still under the lock.
        with self._lock:
            for table in ("profiles", "examples", "applications", "saved_searches",
                          "notifications", "consultants", "house", "opportunities", "clients"):
                self._conn.execute(f"DELETE FROM {table}")
            self._conn.commit()
            try:
                self._conn.execute("VACUUM")    # reclaim/overwrite the freed pages
            except sqlite3.Error:
                pass

    # --- notifications ---
    def save_notification(self, note: Notification) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                # refresh created too (unlike other tables) — a refreshed reminder bumps its
                # timestamp, and list/evict order by created, so the column must follow the data
                "INSERT INTO notifications(id, created, data) VALUES(?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET data=excluded.data, created=excluded.created",
                (note.id, note.created or time.time(), json.dumps(note.to_dict())),
            )
            self._evict("notifications", "id", MAX_NOTIFICATIONS)

    def get_notification(self, note_id: str) -> Notification | None:
        with self._lock:
            row = self._conn.execute("SELECT data FROM notifications WHERE id=?", (note_id,)).fetchone()
        return Notification.from_dict(json.loads(row["data"])) if row else None

    def list_notifications(self) -> list[Notification]:
        with self._lock:
            rows = self._conn.execute("SELECT data FROM notifications ORDER BY created DESC").fetchall()
        return [Notification.from_dict(json.loads(r["data"])) for r in rows]

    def delete_notification(self, note_id: str) -> None:
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM notifications WHERE id=?", (note_id,))

    def close(self) -> None:
        self._conn.close()
