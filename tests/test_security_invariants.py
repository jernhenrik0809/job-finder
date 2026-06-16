"""Security-regression suite — enforce the app's three core invariants on every CI run:

  1. No configured secret (API key) ever appears in a response — swept on GET endpoints AND
     driven through the search-warning path (where a failed keyed request once leaked the
     key embedded in the request URL).
  2. No outbound host outside a known allow-list — enforced at RUNTIME (every host a source
     actually contacts, so f-string / variable hosts can't slip past a source-text scan),
     plus a cheap literal-string lint as a secondary check.
  3. No auto-submit / browser-automation machinery imported — a best-effort smoke test; the
     real "drafts, never sends" guarantee is design + the runtime host allow-list above.
"""
import dataclasses
import importlib
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import requests
from fastapi.testclient import TestClient

import jobfinder.config as config
import jobfinder.web as web
from jobfinder.sources.adzuna import AdzunaSource
from jobfinder.sources.arbeitnow import ArbeitnowSource
from jobfinder.sources.jooble import JoobleSource
from jobfinder.sources.jsearch import JSearchSource
from jobfinder.sources.linkedin import LinkedInSource
from jobfinder.sources.remotive import RemotiveSource

_PKG = Path(__file__).resolve().parents[1] / "jobfinder"
_PY_FILES = sorted(_PKG.rglob("*.py"))

# Sentinels derived from the single source of truth (config.SECRET_FIELDS), so a newly
# added secret field is automatically forced into the no-leak sweep.
_SENTINELS = {name: f"SENTINEL-{name.upper().replace('_', '-')}" for name in config.SECRET_FIELDS}

# Every host the app is permitted to contact: the job-board APIs, the Anthropic API
# (anthropic SDK), and loopback. Kept minimal — only hosts the code actually uses.
_ALLOWED_HOSTS = {
    "api.adzuna.com", "developer.adzuna.com",       # Adzuna source + signup-doc URL
    "jooble.org",                                   # Jooble source
    "jsearch.p.rapidapi.com", "rapidapi.com",       # JSearch source + signup-doc URL
    "remotive.com",                                 # Remotive source
    "www.arbeitnow.com",                            # Arbeitnow source
    "www.linkedin.com",                             # LinkedIn guest source
    "api.anthropic.com",                            # Claude (anthropic SDK)
    "127.0.0.1", "localhost",                       # loopback
}


# --- 1) no secret leaks into a response -----------------------------------

def test_sentinels_cover_every_secret_field():
    # drift guard: adding a key to config.SECRET_FIELDS forces it into the sweep
    assert set(_SENTINELS) == set(config.SECRET_FIELDS)


def test_no_secret_in_get_responses(monkeypatch):
    patched = dataclasses.replace(web.settings, **_SENTINELS)
    monkeypatch.setattr(web, "settings", patched)
    client = TestClient(web.app)

    paths = {"/api/health", "/api/sources", "/api/draft-config"}
    for route in web.app.routes:
        if "GET" in (getattr(route, "methods", None) or set()) and "{" not in getattr(route, "path", "{"):
            paths.add(route.path)

    blob = "\n".join(client.get(p).text for p in sorted(paths) if client.get(p).status_code == 200)
    for name, value in _SENTINELS.items():
        assert value not in blob, f"secret '{name}' leaked into a GET response"


def test_no_secret_in_search_warnings(monkeypatch):
    """A keyed source whose request fails must not echo its key (which rides in the request
    URL as a query param / path) into the /api/search warnings."""
    patched = dataclasses.replace(config.settings, **_SENTINELS)
    monkeypatch.setattr(config, "settings", patched)
    monkeypatch.setattr(web, "settings", patched)
    for name in ("adzuna", "jooble", "jsearch"):
        mod = importlib.import_module(f"jobfinder.sources.{name}")
        monkeypatch.setattr(mod, "settings", patched, raising=False)

    # Fail every request with the worst case: a message embedding the fully-prepared URL
    # (the real leak vector — urllib3 puts the key-bearing URL into the exception text).
    def boom(self, method, url, *a, **k):
        pr = requests.models.PreparedRequest()
        try:
            pr.prepare_url(url, k.get("params"))
        except Exception:
            pr.url = url
        raise requests.exceptions.ConnectionError(f"Max retries exceeded with url: {pr.url}")

    monkeypatch.setattr(requests.sessions.Session, "request", boom)

    client = TestClient(web.app)
    cv_id = client.post("/api/upload-text", data={"text": "Python developer with Django and AWS."}).json()["cv_id"]
    r = client.post("/api/search", json={
        "cv_id": cv_id, "keywords": "python", "sources": ["adzuna", "jooble", "jsearch"], "min_score": 0,
    })
    body = r.text
    assert r.status_code == 200 and "warnings" in body          # the failing sources did warn
    for name, value in _SENTINELS.items():
        assert value not in body, f"secret '{name}' leaked into a search warning"


# --- 2) runtime egress allow-list (authoritative) -------------------------

class _FakeResp:
    status_code = 200
    text = ""
    content = b""
    headers: dict = {}
    def raise_for_status(self): pass
    def json(self): return {}


def test_runtime_egress_allowlist(monkeypatch):
    """Patch the network layer to record every host a source actually contacts (catching
    f-string / variable hosts that a source-text scan would miss) and assert all are allowed."""
    contacted: list[str] = []

    def record(self, method, url, *a, **k):
        contacted.append((urlparse(url).hostname or "").lower())
        return _FakeResp()

    monkeypatch.setattr(requests.sessions.Session, "request", record)
    # don't let any polite-delay sleeps slow the test
    for name in ("linkedin",):
        mod = importlib.import_module(f"jobfinder.sources.{name}")
        if hasattr(mod, "time"):
            monkeypatch.setattr(mod.time, "sleep", lambda *_: None, raising=False)

    sources = [
        RemotiveSource(), ArbeitnowSource(),
        AdzunaSource(app_id="x", app_key="y"), JoobleSource(api_key="k"),
        JSearchSource(api_key="k"), LinkedInSource(),
    ]
    for s in sources:
        try:
            s.search("python developer", limit=2)
        except Exception:
            pass        # parsing the empty fake response may raise — we only need the host

    assert contacted, "no source made a request (test would be vacuous)"
    unexpected = sorted({h for h in contacted if h and h not in _ALLOWED_HOSTS})
    assert not unexpected, f"source contacted non-allow-listed host(s): {unexpected}"


# --- 3) no auto-submit machinery (best-effort smoke test) -----------------

# Anchored to import statements / call sites so a *comment* mentioning a library
# ("we deliberately never use selenium") doesn't trip the test.
_FORBIDDEN = re.compile(
    r"(?:^|\n)\s*(?:import|from)\s+(?:smtplib|imaplib|aiosmtplib|selenium|playwright|mechanize|pyautogui)\b"
    r"|\.send_keys\s*\(",
    re.I,
)


def test_no_auto_submit_machinery():
    offenders = [f"{f.name}: {m.group(0).strip()!r}"
                 for f in _PY_FILES
                 for m in _FORBIDDEN.finditer(f.read_text(encoding="utf-8"))]
    assert not offenders, f"auto-submit / browser-automation machinery imported: {offenders}"


# --- secondary literal lint for outbound hosts ----------------------------

_URL_RE = re.compile(r"https?://([A-Za-z0-9.\-]+)")


def test_no_unexpected_outbound_host_literal():
    found = {}
    for f in _PY_FILES:
        for host in _URL_RE.findall(f.read_text(encoding="utf-8")):
            if "." in host or host == "localhost":      # skip bare prose placeholders
                found.setdefault(host.lower(), f.name)
    unexpected = {h: src for h, src in found.items() if h not in _ALLOWED_HOSTS}
    assert not unexpected, f"literal outbound host outside the allow-list: {unexpected}"
