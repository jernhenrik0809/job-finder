"""Repository interface over the app's durable state.

Two backends implement this: MemoryStore (ephemeral, today's behaviour) and
SqliteStore (persists across restarts). The web layer talks only to this interface,
never to module-global dicts. Caps bound memory/DB growth for a single-user app.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from ..applications import Application
from ..clients import Client
from ..consultants import Consultant
from ..cv_parser import CVProfile
from ..house import House
from ..notifications import Notification
from ..opportunities import Opportunity
from ..saved_searches import SavedSearch

MAX_PROFILES = 50
MAX_EXAMPLES = 10
MAX_APPLICATIONS = 200
MAX_SAVED_SEARCHES = 40
MAX_NOTIFICATIONS = 100
MAX_CONSULTANTS = 300            # the bench — sized well above a ~100-consultant house
MAX_OPPORTUNITIES = 500          # pursued projects (postings + warm leads)
MAX_CLIENTS = 500                # client/account relationships (direct-warm layer)


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
    @abstractmethod
    def update_saved_search(self, search_id: str, mutator) -> SavedSearch | None:
        """Atomically load → ``mutator(search)`` → save under a single lock, so a
        background sweep and a foreground run/seen can't clobber each other's
        seen_ids/new_count (lost update). Returns the updated search, or None if it's gone."""
        ...

    # --- consultants (the house's bench) ---
    @abstractmethod
    def save_consultant(self, consultant: Consultant) -> None: ...
    @abstractmethod
    def get_consultant(self, consultant_id: str) -> Consultant | None: ...
    @abstractmethod
    def list_consultants(self) -> list[Consultant]: ...
    @abstractmethod
    def delete_consultant(self, consultant_id: str) -> None: ...

    # --- house (single-row identity that grounds proposals) ---
    @abstractmethod
    def get_house(self) -> House | None: ...
    @abstractmethod
    def save_house(self, house: House) -> None: ...

    # --- opportunities (pursued projects + the proposal audit trail) ---
    @abstractmethod
    def save_opportunity(self, opp: Opportunity) -> None: ...
    @abstractmethod
    def get_opportunity(self, opp_id: str) -> Opportunity | None: ...
    @abstractmethod
    def list_opportunities(self) -> list[Opportunity]: ...
    @abstractmethod
    def delete_opportunity(self, opp_id: str) -> None: ...
    @abstractmethod
    def get_opportunity_by_posting(self, source: str, source_uid: str) -> Opportunity | None:
        """Find an existing opportunity for an ingested posting by (source, source_uid) — the
        idempotency lookup so a re-surfaced posting updates its row instead of duplicating."""
        ...
    @abstractmethod
    def update_opportunity(self, opp_id: str, mutator) -> Opportunity | None:
        """Atomically load → ``mutator(opp)`` → save under one lock, so a background sweep and a
        foreground edit can't clobber each other's events/status. Returns the updated opp or None."""
        ...

    # --- clients (the direct-warm relationship layer) ---
    @abstractmethod
    def save_client(self, client: Client) -> None: ...
    @abstractmethod
    def get_client(self, client_id: str) -> Client | None: ...
    @abstractmethod
    def list_clients(self) -> list[Client]: ...
    @abstractmethod
    def delete_client(self, client_id: str) -> None: ...

    # --- data rights (export / wipe everything) ---
    @abstractmethod
    def export_all(self) -> dict:
        """A serializable bundle of EVERY user-data table (one key per table). Excludes API
        keys — those live outside the DB. The reflective data-rights test asserts this bundle
        names every table, so a newly-added entity can't silently escape export/erasure."""
        ...
    @abstractmethod
    def delete_all(self) -> None:
        """Permanently delete all stored user data (every table). API keys are not touched."""
        ...

    # --- notifications (the in-app alert inbox) ---
    @abstractmethod
    def save_notification(self, note: Notification) -> None: ...
    @abstractmethod
    def get_notification(self, note_id: str) -> Notification | None: ...
    @abstractmethod
    def list_notifications(self) -> list[Notification]: ...
    @abstractmethod
    def delete_notification(self, note_id: str) -> None: ...

    def close(self) -> None:  # optional; SqliteStore overrides
        pass
