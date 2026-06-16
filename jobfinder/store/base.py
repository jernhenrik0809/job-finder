"""Repository interface over the app's durable state.

Two backends implement this: MemoryStore (ephemeral, today's behaviour) and
SqliteStore (persists across restarts). The web layer talks only to this interface,
never to module-global dicts. Caps bound memory/DB growth for a single-user app.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from ..cv_parser import CVProfile
from ..drafts import ApplicationDraft

MAX_PROFILES = 50
MAX_EXAMPLES = 10
MAX_DRAFTS = 100


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

    # --- application drafts (the outbox) ---
    @abstractmethod
    def save_draft(self, draft: ApplicationDraft) -> None: ...
    @abstractmethod
    def get_draft(self, draft_id: str) -> ApplicationDraft | None: ...
    @abstractmethod
    def list_drafts(self) -> list[ApplicationDraft]: ...
    @abstractmethod
    def delete_draft(self, draft_id: str) -> None: ...

    def close(self) -> None:  # optional; SqliteStore overrides
        pass
