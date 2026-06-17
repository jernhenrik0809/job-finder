"""Runtime-settable credentials, so a non-coder can paste API keys in the Settings page
instead of setting environment variables.

Resolution order for every secret: **environment variable (wins)** → a local
``secrets.json`` the user can write from the UI → ``None``. Environment variables always
take precedence, so existing env-based setups (and the test suite) are unaffected.

The local file lives in the app data dir with owner-only permissions. Secrets are **never**
stored in the application database and **never** returned in an API response — only their
*presence* (a boolean) is ever exposed. See docs/PRIVACY.md.
"""
from __future__ import annotations

import json
import os
import threading

from .config import settings

_LOCK = threading.Lock()
# Resolved lazily/patchably so tests can point it at a tmp path (never the real data dir).
_FILE = settings.data_dir / "secrets.json"

# logical secret name → the environment variable(s) that can supply it (first match wins)
_ENV = {
    "anthropic_key": ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"),
    "rapidapi_key": ("RAPIDAPI_KEY", "JSEARCH_API_KEY"),
    "adzuna_app_id": ("ADZUNA_APP_ID",),
    "adzuna_app_key": ("ADZUNA_APP_KEY",),
    "jooble_key": ("JOOBLE_API_KEY",),
    "careerjet_affid": ("CAREERJET_AFFID",),
    "freelancer_token": ("FREELANCER_TOKEN",),
    "model": ("JOBFINDER_MODEL",),
}

# Fields the Settings page may write. (model is a tier choice, not a secret, but shares the store.)
SETTABLE = tuple(_ENV.keys())

_overlay: dict | None = None


def _load() -> dict:
    global _overlay
    if _overlay is None:
        try:
            _overlay = json.loads(_FILE.read_text(encoding="utf-8"))
            if not isinstance(_overlay, dict):
                _overlay = {}
        except Exception:
            _overlay = {}
    return _overlay


def get(name: str, default: str | None = None) -> str | None:
    """Resolve a secret: env var (wins) → local file → default."""
    for env in _ENV.get(name, ()):
        v = os.environ.get(env)
        if v:
            return v
    v = _load().get(name)
    return v if v else default


def set_many(values: dict) -> None:
    """Persist user-entered values to the local file. A value of None leaves a field
    unchanged; an empty string clears it. Unknown keys are ignored."""
    with _LOCK:
        cur = dict(_load())
        for k, v in values.items():
            if k not in _ENV or v is None:
                continue
            v = str(v).strip()
            if v == "":
                cur.pop(k, None)
            else:
                cur[k] = v
        _FILE.parent.mkdir(parents=True, exist_ok=True)
        _FILE.write_text(json.dumps(cur), encoding="utf-8")
        try:
            os.chmod(_FILE, 0o600)          # owner-only (best effort; no-op on some filesystems)
        except OSError:
            pass
        global _overlay
        _overlay = cur


def is_env(name: str) -> bool:
    """True if this secret is supplied by an environment variable (so it can't be
    overridden from the Settings file — env always wins)."""
    return any(os.environ.get(e) for e in _ENV.get(name, ()))


def reset_cache() -> None:
    """Drop the in-memory overlay cache (used by tests after re-pointing the file)."""
    global _overlay
    _overlay = None


def model() -> str:
    return get("model") or settings.model


def present() -> dict:
    """Source key-presence for the UI source-gating — keyed by *source name* (booleans
    only, never the values), so it matches the source checkboxes."""
    return {
        "jsearch": bool(get("rapidapi_key")),
        "adzuna": bool(get("adzuna_app_id") and get("adzuna_app_key")),
        "jooble": bool(get("jooble_key")),
        "careerjet": bool(get("careerjet_affid")),
        "freelancer": bool(get("freelancer_token")),
    }


def anthropic_present() -> bool:
    return bool(get("anthropic_key"))
