"""Network-boundary hardening for the local-first server.

A personal app bound to localhost is still reachable by any website the user
visits: a malicious page can run ``fetch('http://127.0.0.1:8000/api/...')`` in the
background. Two independent, always-on layers guard the boundary:

1. **Host allow-list** — the request's ``Host`` must be a name we trust (loopback,
   plus any host the user explicitly declared via ``JOBFINDER_ALLOWED_HOSTS``). This
   is the real **DNS-rebinding** defense: in a rebinding attack the browser sends the
   *attacker's* domain as ``Host`` (rebound to the victim's IP), which is not on the
   list, so it is rejected. This check is enforced **even when LAN serving is enabled**
   — enabling LAN only lets the server *bind* a public address; it never widens the
   set of accepted Hosts to "anything".
2. **Same-origin** — any request carrying an ``Origin`` not same-origin with the host
   it targeted is rejected. This stops ordinary cross-site CSRF fetches (which keep the
   loopback ``Host`` but carry the attacker's ``Origin``). Non-browser clients (curl,
   the test client) send no ``Origin`` and pass through.

The decision logic lives in :func:`check_request` (pure, unit-tested without a
server); :class:`LocalSecurityMiddleware` is the thin ASGI wrapper.
"""
from __future__ import annotations

from collections.abc import Iterable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import PlainTextResponse

# Hostnames that are always the user's own machine. "testserver" is the host the
# Starlette/FastAPI TestClient uses — allowing it keeps the suite server-free.
_LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1", "[::1]", "testserver"}

# Bind placeholders that are never valid as an accepted Host value.
_WILDCARDS = {"", "0.0.0.0", "::", "[::]"}


def _hostname(authority: str) -> str:
    """Extract the bare lowercased hostname from a Host header or Origin value.

    Strips scheme, any path, userinfo (``user:pass@host``) and port, and a trailing
    dot. Handles IPv6 literals like ``[::1]:8000``. Returns "" for empty input.
    """
    h = (authority or "").strip().lower()
    if not h:
        return ""
    if "://" in h:                      # an Origin like "http://host:port"
        h = h.split("://", 1)[1]
    h = h.split("/", 1)[0]              # drop any path / trailing slash
    if "@" in h:                        # drop userinfo — host is the part AFTER '@'
        h = h.rsplit("@", 1)[1]
    if h.startswith("["):               # IPv6 literal, optionally with :port
        host = h[: h.index("]") + 1] if "]" in h else h
    else:
        host = h.rsplit(":", 1)[0] if ":" in h else h
    return host.rstrip(".")             # localhost. == localhost


def build_allowed_hosts(extra: Iterable[str] | None = None) -> set[str]:
    """The set of Host names the server will accept: loopback plus any declared
    extras (normalised; wildcard/bind placeholders dropped)."""
    hosts = set(_LOOPBACK_HOSTS)
    for raw in extra or []:
        name = _hostname(raw)
        if name and name not in _WILDCARDS:
            hosts.add(name)
    return hosts


def check_request(host_header: str, origin_header: str, allowed_hosts: Iterable[str]) -> tuple[bool, int, str]:
    """Decide whether a request may proceed.

    Returns ``(ok, status_code, message)``. ``ok`` True means allow; otherwise the
    status/message describe the refusal. ``allowed_hosts`` is the full accepted set
    (use :func:`build_allowed_hosts`).
    """
    allowed = set(allowed_hosts)
    host_name = _hostname(host_header)

    # 1) Host allow-list — DNS-rebinding defense, always on. A rebound attacker
    #    domain arrives as a non-allowed Host and is rejected here.
    if host_name not in allowed:
        return (False, 400,
                f"Host '{host_name or '?'}' is not allowed. Job Finder serves loopback only; "
                "to reach it by another name/IP, add it to JOBFINDER_ALLOWED_HOSTS.")

    # 2) Same-origin — a cross-site Origin means another site's page is calling us.
    if origin_header:
        if _hostname(origin_header) != host_name:
            return (False, 403, "Cross-origin request rejected (same-origin only).")

    return (True, 200, "")


class LocalSecurityMiddleware(BaseHTTPMiddleware):
    """Enforce :func:`check_request` on every HTTP request."""

    def __init__(self, app, allowed_hosts: Iterable[str] | None = None):
        super().__init__(app)
        self.allowed_hosts = set(allowed_hosts) if allowed_hosts else set(_LOOPBACK_HOSTS)

    async def dispatch(self, request, call_next):
        ok, status, message = check_request(
            request.headers.get("host", ""),
            request.headers.get("origin", ""),
            self.allowed_hosts,
        )
        if not ok:
            return PlainTextResponse(message, status_code=status)
        return await call_next(request)
