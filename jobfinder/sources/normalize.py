"""Shared normalisation helpers for job sources.

These were previously copy-pasted into nearly every source module (a `_strip_html` in
~17 files, plus near-identical date parsers). Centralising them removes the duplication
and gives one place to harden parsing. All helpers are defensive: they coerce/guard their
input and never raise on malformed upstream data.
"""
from __future__ import annotations

import html
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def strip_html(text) -> str:
    """HTML fragment → clean single-line text. Coerces non-strings (some APIs return a
    number or null where text is expected) instead of raising."""
    cleaned = _TAG.sub(" ", str(text or ""))
    return _WS.sub(" ", html.unescape(cleaned)).strip()


def rfc822_date(value) -> str:
    """An RSS/HTTP RFC-822 date (e.g. 'Tue, 16 Jun 2026 20:31:47 +0000') → 'YYYY-MM-DD'."""
    try:
        return parsedate_to_datetime(value).date().isoformat()
    except (TypeError, ValueError):
        return ""


def epoch_date(value) -> str:
    """A Unix epoch (seconds, or milliseconds if it's clearly too large) → 'YYYY-MM-DD'."""
    try:
        ts = int(value)
    except (TypeError, ValueError):
        return ""
    if ts > 10_000_000_000:           # milliseconds → seconds
        ts //= 1000
    try:
        return datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()
    except (ValueError, OverflowError, OSError):
        return ""


def iso_date(value) -> str:
    """A loosely-ISO date/datetime string → its 'YYYY-MM-DD' prefix (coerces non-strings)."""
    return str(value or "")[:10]
