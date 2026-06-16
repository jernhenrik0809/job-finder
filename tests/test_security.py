"""Tests for the network-boundary hardening (same-origin + Host allow-list)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from jobfinder.security import check_request, build_allowed_hosts, _hostname, _LOOPBACK_HOSTS
from jobfinder.web import app

client = TestClient(app)   # app's middleware runs with the default loopback allow-set (test env)

LOOPBACK = build_allowed_hosts()          # just the loopback/testserver set
WITH_LAN = build_allowed_hosts(["192.168.1.50"])   # user declared one LAN IP


# --- hostname parsing -----------------------------------------------------

def test_hostname_strips_scheme_port_userinfo_and_dot():
    assert _hostname("127.0.0.1:8000") == "127.0.0.1"
    assert _hostname("http://evil.com:1234") == "evil.com"
    assert _hostname("[::1]:8000") == "[::1]"
    assert _hostname("LocalHost") == "localhost"
    assert _hostname("localhost.") == "localhost"            # trailing dot normalised
    assert _hostname("http://user:pass@evil.com") == "evil.com"   # userinfo stripped
    assert _hostname("http://evil.com:80@127.0.0.1") == "127.0.0.1"
    assert _hostname("") == ""


def test_build_allowed_hosts_drops_wildcards():
    s = build_allowed_hosts(["0.0.0.0", "::", "", "Example.LAN", "10.0.0.5:8000"])
    assert "example.lan" in s and "10.0.0.5" in s
    assert "0.0.0.0" not in s and "::" not in s
    assert _LOOPBACK_HOSTS <= s                               # loopback always included


# --- pure decision function ------------------------------------------------

def test_loopback_no_origin_allowed():
    ok, status, _ = check_request("127.0.0.1:8000", "", LOOPBACK)
    assert ok and status == 200


def test_foreign_host_blocked():
    ok, status, msg = check_request("192.168.1.50:8000", "", LOOPBACK)
    assert not ok and status == 400 and "allowed_hosts" in msg.lower()


def test_declared_lan_host_allowed():
    ok, status, _ = check_request("192.168.1.50:8000", "http://192.168.1.50:8000", WITH_LAN)
    assert ok and status == 200


def test_same_origin_allowed():
    ok, status, _ = check_request("127.0.0.1:8000", "http://127.0.0.1:8000", LOOPBACK)
    assert ok and status == 200


def test_cross_origin_blocked():
    # a malicious site fetching our localhost API carries its own Origin
    ok, status, msg = check_request("127.0.0.1:8000", "http://evil.example.com", LOOPBACK)
    assert not ok and status == 403 and "cross-origin" in msg.lower()


def test_dns_rebinding_blocked_even_with_lan_enabled():
    # THE core fix: enabling LAN serving must NOT accept an arbitrary Host. In a
    # rebinding attack the browser sends the attacker's domain as BOTH Host and
    # Origin (their domain rebound to our IP) — same-origin alone would pass it, so
    # the always-on Host allow-list must reject it.
    ok, status, _ = check_request("attacker.com", "http://attacker.com", WITH_LAN)
    assert not ok and status == 400


def test_ipv6_loopback_allowed():
    ok, _, _ = check_request("[::1]:8000", "", LOOPBACK)
    assert ok


# --- live middleware via the app ------------------------------------------

def test_middleware_allows_normal_request():
    assert client.get("/api/health").status_code == 200


def test_middleware_blocks_cross_site_fetch():
    r = client.get("/api/health", headers={"Origin": "http://attacker.test"})
    assert r.status_code == 403


def test_middleware_allows_same_origin_fetch():
    r = client.get("/api/health", headers={"Origin": "http://testserver"})
    assert r.status_code == 200


def test_middleware_blocks_foreign_host():
    r = client.get("/api/health", headers={"Host": "evil.test"})
    assert r.status_code == 400
