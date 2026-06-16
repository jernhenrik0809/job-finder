"""Repository interface over the app's durable state.

Two backends implement this: MemoryStore (ephemeral, today's behaviour) and
SqliteStore (persists across restarts). The web layer talks only to this interface,
never to module-global dicts. Caps bound memory/DB growth for a single-user app.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from ..applications import Application
from ..cv_parser import CVProfile
from ..saved_searches import SavedSearch

MAX_PROFILES = 50
MAX_EXAMPLES = 10
MAX_APPLICATIONS = 200
MAX_SAVED_SEARCHES = 40


class Store(ABC):
    # --- profiles ---
    @abstractmethod
    def save_profile(self, cv_id: str, profile: CVProfile) -> None: ...
    @abstractmethod
    def get_profile(self, cv_id: str) -> CVProfile | None: ...

    # --- style examples (plain dicts: {id, name, text, chars}) ---
    @abstractmethod
    def save_example(self, example: dict) -> None: ...
    @abstractmethod
    def list_examples(self) -> list[dict]: ...
    @abstractmethod
    def delete_example(self, example_id: str) -> None: ...

    # --- applications (the pipeline / outbox) ---
    @abstractmethod
    def save_application(self, app: Application) -> None: ...
    @abstractmethod
    def get_application(self, app_id: str) -> Application | None: ...
    @abstractmethod
    def list_applications(self) -> list[Application]: ...
    @abstractmethod
    def delete_application(self, app_id: str) -> None: ...

    # --- saved searches ---
    @abstractmethod
    def save_saved_search(self, search: SavedSearch) -> None: ...
    @abstractmethod
    def get_saved_search(self, search_id: str) -> SavedSearch | None: ...
    @abstractmethod
    def list_saved_searches(self) -> list[SavedSearch]: ...
    @abstractmethod
    def delete_saved_search(self, search_id: str) -> None: ...

    def close(self) -> None:  # optional; SqliteStore overrides
        pass
