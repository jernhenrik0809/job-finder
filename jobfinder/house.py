"""House = the consulting house's own identity — a single-row record that grounds every
proposal with a consistent voice and signatory (the third-person "we" a bid is written in).

There is exactly one House per local install (single-tenant), stored under a fixed id.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, fields

HOUSE_ID = "house"      # single-row: one house per local install


@dataclass
class House:
    name: str = ""
    tagline: str = ""
    voice: str = ""              # tone/style guidance fed to the proposal generator
    signatory: str = ""         # who signs proposals (name + title)
    boilerplate: str = ""       # standard "about us" paragraph
    contact: str = ""
    website: str = ""
    id: str = HOUSE_ID
    created: float = 0.0
    updated: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "House":
        allowed = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in allowed})
