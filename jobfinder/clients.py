"""Client = an organisation the house bids to / works with (the direct-warm relationship layer).

Secondary to the posting-driven primary channel, but it is where repeat business and the
"don't bid this account" guardrail live. Contacts are EMBEDDED on the client record (one blob
per row — no separate contacts table), matching the store's one-blob-per-row pattern.
"""
from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, field, asdict, fields


@dataclass
class Client:
    name: str
    sector: str = ""
    contacts: list[dict] = field(default_factory=list)   # [{name, role, email, phone}]
    do_not_bid: bool = False                             # a hard "don't pursue this account" flag
    past_projects: list[str] = field(default_factory=list)
    notes: str = ""
    created: float = 0.0
    updated: float = 0.0
    id: str = field(default_factory=lambda: secrets.token_urlsafe(8))

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Client":
        allowed = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in allowed})


def _clean_contacts(contacts) -> list[dict]:
    """Keep only well-formed contact dicts with at least a name; coerce fields to strings."""
    out: list[dict] = []
    for ct in contacts or []:
        if not isinstance(ct, dict):
            continue
        name = str(ct.get("name") or "").strip()
        if not name:
            continue
        out.append({"name": name, "role": str(ct.get("role") or "").strip(),
                    "email": str(ct.get("email") or "").strip(), "phone": str(ct.get("phone") or "").strip()})
    return out


def new_client(name: str, **kw) -> Client:
    now = time.time()
    if "contacts" in kw:
        kw["contacts"] = _clean_contacts(kw["contacts"])
    return Client(name=(name or "").strip() or "Unnamed client", created=now, updated=now, **kw)
