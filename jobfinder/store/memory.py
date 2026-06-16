"""In-memory store — ephemeral, fast, used for tests and the privacy-paranoid mode.

This is the behaviour the app had before persistence: dicts that vanish on restart.
Dict insertion order gives us FIFO eviction; re-assigning an existing key (an
application update) preserves its position.
"""
from __future__ import annotations

from .base import Store, MAX_PROFILES, MAX_EXAMPLES, MAX_APPLICATIONS
from ..applications import Application
from ..cv_parser import CVProfile


def _evict(d: dict, cap: int) -> None:
    while len(d) > cap:
        d.pop(next(iter(d)))


class MemoryStore(Store):
    def __init__(self) -> None:
        self._profiles: dict[str, CVProfile] = {}
        self._examples: dict[str, dict] = {}
        self._apps: dict[str, Application] = {}

    def save_profile(self, cv_id: str, profile: CVProfile) -> None:
        self._profiles[cv_id] = profile
        _evict(self._profiles, MAX_PROFILES)

    def get_profile(self, cv_id: str) -> CVProfile | None:
        return self._profiles.get(cv_id)

    def save_example(self, example: dict) -> None:
        self._examples[example["id"]] = example
        _evict(self._examples, MAX_EXAMPLES)

    def list_examples(self) -> list[dict]:
        return list(self._examples.values())

    def delete_example(self, example_id: str) -> None:
        self._examples.pop(example_id, None)

    def save_application(self, app: Application) -> None:
        self._apps[app.id] = app
        _evict(self._apps, MAX_APPLICATIONS)

    def get_application(self, app_id: str) -> Application | None:
        return self._apps.get(app_id)

    def list_applications(self) -> list[Application]:
        return list(self._apps.values())

    def delete_application(self, app_id: str) -> None:
        self._apps.pop(app_id, None)
