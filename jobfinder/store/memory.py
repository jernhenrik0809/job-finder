"""In-memory store — ephemeral, fast, used for tests and the privacy-paranoid mode.

This is the behaviour the app had before persistence: dicts that vanish on restart.
Dict insertion order gives us FIFO eviction; re-assigning an existing key (an
application update) preserves its position.
"""
from __future__ import annotations

import threading

from .base import (Store, MAX_PROFILES, MAX_EXAMPLES, MAX_APPLICATIONS, MAX_SAVED_SEARCHES,
                   MAX_NOTIFICATIONS)
from ..applications import Application
from ..cv_parser import CVProfile
from ..notifications import Notification
from ..saved_searches import SavedSearch


def _evict(d: dict, cap: int) -> None:
    while len(d) > cap:
        d.pop(next(iter(d)))


class MemoryStore(Store):
    def __init__(self) -> None:
        self._profiles: dict[str, CVProfile] = {}
        self._examples: dict[str, dict] = {}
        self._apps: dict[str, Application] = {}
        self._searches: dict[str, SavedSearch] = {}
        self._notes: dict[str, Notification] = {}
        # A single non-reentrant lock guards every dict access, so a background alert sweep
        # writing (save_notification / update_saved_search) can't race a concurrent export_all
        # iteration ("dictionary changed size") or a delete_all clear. No method calls another
        # while holding the lock, so non-reentrancy is safe.
        self._lock = threading.Lock()

    def save_profile(self, cv_id: str, profile: CVProfile) -> None:
        with self._lock:
            self._profiles[cv_id] = profile
            _evict(self._profiles, MAX_PROFILES)

    def get_profile(self, cv_id: str) -> CVProfile | None:
        with self._lock:
            return self._profiles.get(cv_id)

    def save_example(self, example: dict) -> None:
        with self._lock:
            self._examples[example["id"]] = example
            _evict(self._examples, MAX_EXAMPLES)

    def list_examples(self) -> list[dict]:
        with self._lock:
            return list(self._examples.values())

    def delete_example(self, example_id: str) -> None:
        with self._lock:
            self._examples.pop(example_id, None)

    def save_application(self, app: Application) -> None:
        with self._lock:
            self._apps[app.id] = app
            _evict(self._apps, MAX_APPLICATIONS)

    def get_application(self, app_id: str) -> Application | None:
        with self._lock:
            return self._apps.get(app_id)

    def list_applications(self) -> list[Application]:
        with self._lock:
            return list(self._apps.values())

    def delete_application(self, app_id: str) -> None:
        with self._lock:
            self._apps.pop(app_id, None)

    def save_saved_search(self, search: SavedSearch) -> None:
        with self._lock:
            self._searches[search.id] = search
            _evict(self._searches, MAX_SAVED_SEARCHES)

    def get_saved_search(self, search_id: str) -> SavedSearch | None:
        with self._lock:
            return self._searches.get(search_id)

    def list_saved_searches(self) -> list[SavedSearch]:
        with self._lock:
            return list(self._searches.values())

    def delete_saved_search(self, search_id: str) -> None:
        with self._lock:
            self._searches.pop(search_id, None)

    def update_saved_search(self, search_id: str, mutator) -> SavedSearch | None:
        with self._lock:
            s = self._searches.get(search_id)
            if s is None:
                return None
            mutator(s)
            return s

    def export_all(self) -> dict:
        with self._lock:
            return {
                "profiles": {cid: p.to_dict() for cid, p in self._profiles.items()},
                "examples": list(self._examples.values()),
                "applications": [a.to_dict() for a in self._apps.values()],
                "saved_searches": [s.to_dict() for s in self._searches.values()],
                "notifications": [n.to_dict() for n in self._notes.values()],
            }

    def delete_all(self) -> None:
        with self._lock:
            self._profiles.clear()
            self._examples.clear()
            self._apps.clear()
            self._searches.clear()
            self._notes.clear()

    def save_notification(self, note: Notification) -> None:
        with self._lock:
            self._notes[note.id] = note
            _evict(self._notes, MAX_NOTIFICATIONS)

    def get_notification(self, note_id: str) -> Notification | None:
        with self._lock:
            return self._notes.get(note_id)

    def list_notifications(self) -> list[Notification]:
        with self._lock:
            return list(reversed(self._notes.values()))      # newest first

    def delete_notification(self, note_id: str) -> None:
        with self._lock:
            self._notes.pop(note_id, None)
