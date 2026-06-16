# Security

Job Finder runs entirely on your machine and handles sensitive data (your CV, cover
letters, and pipeline). This document describes the threat model, the protections in
place, and how to report a problem.

## Threat model

Job Finder is a **local, single-user** web app: a small server bound to `127.0.0.1`
that your browser talks to. The realistic threats are therefore:

| Threat | Mitigation |
|---|---|
| Another website you're visiting silently calls `http://127.0.0.1:8000/api/...` to read your data (CSRF / DNS-rebinding) | **Same-origin guard** rejects any cross-site request; **Host allow-list** rejects any `Host` that isn't loopback (or a name you explicitly declared). See `jobfinder/security.py`. |
| Binding to the LAN exposes every CV/letter to the network with no auth | `run.py` refuses a non-loopback bind unless you pass `--allow-lan` / set `JOBFINDER_ALLOW_LAN=1`, and even then only answers to `Host`s you list in `JOBFINDER_ALLOWED_HOSTS`. |
| A plaintext CV is left on disk after a crash | Uploads are parsed in memory (`BytesIO`), never written to a temp file. |
| A configured API key leaks into a response | Enforced by CI: no configured secret may appear in any response body (`tests/test_security_invariants.py`). Source error messages report only the error *type*, never the key-bearing request URL. |
| The app quietly phones home / exfiltrates data | Enforced by CI: every host a source contacts at runtime must be on a known allow-list (the job-board APIs + the Anthropic API + loopback). |
| The app auto-applies / sends on your behalf | It never does — see [ETHICS.md](ETHICS.md). A CI smoke test blocks SMTP / browser-automation imports. |

Out of scope: a local attacker who already has code execution or filesystem access on
your machine, and the security of the upstream job boards / Anthropic.

## Data egress

There is **one** egress, and only if you opt in: with an `ANTHROPIC_API_KEY` set and the
**Use Claude** option on, the cover-letter / résumé-tailoring path sends your CV text,
any uploaded style examples, and the job description to Anthropic. The UI discloses this,
and a **redact contact details** toggle (on by default) masks email / phone / links
first. With no key set, nothing leaves your machine. See [PRIVACY.md](PRIVACY.md).

## CI security-regression suite

`tests/test_security_invariants.py` mechanically enforces, on every push, that: (1) no
secret appears in a response, (2) no source contacts a non-allow-listed host, and (3) no
auto-submit machinery is imported. These run with the normal `pytest` suite.

## Reporting a vulnerability

This is a personal/educational project. If you find a security issue, please open a
GitHub issue describing it (omit any real secrets), or contact the maintainer privately
for anything sensitive. There is no bug-bounty program.
