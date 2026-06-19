# Decisions log — Job Finder → Consulting-House Pursuit Engine

The significant decisions taken while evolving the local job-matcher into a consulting-house
pursuit engine, with the reasoning behind each so a future reader (or operator) understands the
*why*, not just the *what*. Newest-relevant first within each group. Dates are YYYY-MM-DD.

---

## Product & policy

### D1 — No auto-send, ever (the core invariant)
**Decision:** the engine *generates* proposals and supporting documents; a **human always exports
and submits** them. There is no email/browser-automation path, and a runtime egress allow-list
restricts which hosts the app may contact.
**Why:** (1) Danish **Markedsføringsloven §10** prohibits unsolicited electronic marketing without
prior consent, applied to businesses too — auto-blasting bids is plausibly unlawful; (2) platform
ToS (Upwork/LinkedIn/Malt…) ban automated submission, and a ban wipes the channel for the **whole
bench**, not one person; (3) reputational asymmetry — for a *named* house, a stream of auto-sent AI
bids is a permanent brand event. The constraint is the product's **moat**, not a limitation.
**Enforced by:** `tests/test_security_invariants.py` (`test_no_auto_submit_machinery` + the runtime
egress allow-list). `api.anthropic.com` is the only LLM host.

### D2 — Posting-driven is the PRIMARY channel; direct-warm is secondary
**Decision (2026-06-19, corrected):** the core loop ingests postings across all ~30 sources
(gig/consulting/project-focused) → matches the bench → drafts a proposal. The direct-warm path
(paste-in intake + Client/Contact CRM) is a secondary add-on on the *same* pipeline.
**Why:** the owner clarified that postings are the primary source ("we are ingesting postings,
finding matches and writing proposals") — an earlier "direct-warm first" reading was a mutual
misunderstanding. Good consequence: the ingestion half already existed (the 30 sources), so the
new build was the bench + matching + proposal layer.

### D3 — Credibility is the priority; the polished PDF engine (Phase 4) is owner-gated
**Decision:** build the credibility *data* layer (grounded CVs, bid lines, audit trail) now; the
Claude-designed, layout-preserving **PDF proposal/CV production engine stays deferred (Phase 4)**
and is **not** built without an explicit go-ahead.
**Why:** the per-user "rebuild-from-example" PDF engine is high-quality but hard to fully automate
([[pdf-tailoring-engine]] memory); it is a large, separate effort best scheduled deliberately once
the rest is in real use. Export today is plain text / markdown.

### D4 — Bid/no-bid volume control
**Decision:** the sweep only surfaces a gig as a "bench fit" when an eligible consultant clears the
"good match" band (`BENCH_FIT_MIN = 40`, mirroring `matcher.SCORE_BANDS`); an empty result is the
no-bid signal.
**Why:** posting-driven at volume drowns the operator; the gate keeps attention on winnable gigs and
is the structural defense against the "automation scales your *worst* bids" failure mode.

---

## Trust, privacy & compliance

### D5 — GDPR machinery deliberately NOT built
**Decision (2026-06-19, owner steer "we are not worried about that"):** do not build consent/
retention/lawful-basis enforcement. Keep only a free-text `consent_note` and a one-field
`data_origin` provenance on `Consultant` (provenance is free to capture now, impossible to
reconstruct later).
**Why:** the owner accepted the compliance risk for a local, single-operator tool. **Honest residual
risk** (documented, not hidden): the app now stores many real third-party CVs + client PII; if it is
ever shared/multi-user or breached, the exposure is real. Revisit if the tool is shared or productised.

### D6 — Encryption-at-rest deferred (with a defined threshold)
**Decision:** keep the SQLite store plaintext for now; build a pluggable cipher seam later.
**Why:** acceptable while prototyping the owner's own data. **Threshold to revisit:** once the bench
holds real third-party CVs in routine use (which it now can), encryption-at-rest should land —
recommended approach is passphrase-derived AES-GCM via the already-installed `cryptography` lib
(no new dependency; forgotten-passphrase = data-loss, accepted). See [[encryption-at-rest-deferred]].

### D7 — The proposal QA gate is a high-precision *assist*, not an oracle
**Decision:** `guardrails.check_proposal` blocks export on a detected fabrication (a capability
claimed for no proposed consultant / misattributed to the wrong one / unverifiable on a thin corpus
/ a placeholder), in **English and Danish**, and `export` re-runs it (409 on a blocking finding).
But it is explicitly a best-effort assist.
**Why:** it is dictionary + cue based, so it cannot see a fabricated capability whose name is outside
the skills dictionary, nor every unusual phrasing. The honest, real guarantee is **D1** — a human
reviews and sends every proposal; the gate is defense-in-depth. Documented in `check_proposal`'s
docstring. (Hardened after an adversarial review: action-verb phrasing now blocks; the offline
template no longer echoes the brief; non-list skills fail closed; name matching is word-bounded.)

### D8 — Redaction defaults to the server's privacy setting on the proposal path
**Decision:** the proposal endpoints default `redact_pii` to `settings.redact_pii_default` (not the
bare dataclass `False`), since a proposal carries third-party (consultant) + client data sent to Claude.

---

## Architecture & data model

### D9 — `source_uid` de-dup identity (frozen field name)
**Decision:** `Job.id` prefers an optional `source_uid` (namespaced by `source`), falling back to the
legacy `company|title|location` hash. The field name is frozen.
**Why:** sources that reuse one company name (Verama: every assignment is `company="Verama"`) collapsed
distinct postings into one id, so `engine.find_jobs` de-dup silently dropped them (verified repro). The
fix is a hard prerequisite for the Opportunity layer + the posting-driven channel. Backward-compatible.

### D10 — Bench matcher: one shared TF-IDF space + a hard eligibility gate
**Decision:** `bench.rank_consultants` scores many consultants against one project in **one shared
TF-IDF space** (reusing `matcher._tfidf_similarities`, which is already one-to-many — no risky
refactor), with a **pre-rank eligibility gate** (inactive / not-presentable / availability / same-
currency rate ceiling) that zeroes a consultant with an explicit reason.
**Why:** looping `rank_jobs` per consultant refits the vectorizer each call → non-comparable scores.
The hard gate is categorically separate from `matcher.py`'s bounded, never-penalizing nudges (kept
apart on purpose). Fails **open** on unknown data (owner steer); **never** compares rates across
currencies (surfaces a note instead of a wrong number).

### D11 — Entities are JSON-blob-per-row; one shared SQLite connection + process lock
**Decision:** each new entity (`Consultant`, `House`, `Opportunity`, `Client`) is a dataclass with
`to_dict`/`from_dict` (drop-unknown-keys), stored as a JSON blob via `INSERT … ON CONFLICT DO UPDATE`
+ `_evict` caps, on both `MemoryStore` and `SqliteStore`.
**Why:** mirrors the existing `Application` pattern; keeps the store simple and local-first. **Known
ceiling:** a single shared sqlite connection + a global process lock serialises every read/write — a
scalability limit acceptable for a single operator, flagged for the analysis.

### D12 — Opportunity idempotency + append-only audit trail
**Decision:** an `Opportunity` from a posting carries `source`+`source_uid`; `get_opportunity_by_posting`
makes a re-surfaced posting update its row instead of duplicating. Every generate/QA/export/status
action appends an immutable event.
**Why:** re-ingested postings must not spawn duplicates; the audit trail makes "a human reviewed and
sent this" a **durable, defensible record**, not a verbal promise.

### D13 — Margin computed within a single currency only
**Decision:** per-bid-line margin = sell − cost; a `total_margin` is reported only when every staffed
line shares one currency (else null + a note).
**Why:** a cross-currency sum would be silently wrong; surfacing "can't compute" beats a wrong number.

### D14 — Single-tenant, no auth (for now)
**Decision:** one house, one local operator; no login/tenancy. Keep seams clean for a future bigger
house / different operator, but don't build it.
**Why:** the owner may form a bigger house later ("not important for this") — premature tenancy/auth
would be wasted effort. Revisit if a second operator or shared instance is needed (would also make D6
encryption mandatory).

### D15 — Versioned-migration restructure + reflective data-rights test
**Decision:** `_migrate` runs ordered data-backfill steps separate from the idempotent
`CREATE TABLE IF NOT EXISTS` schema; a reflective test asserts every table appears in `export_all()`
and is emptied by `delete_all()`.
**Why:** the old single-int + unconditional-executescript design couldn't express backfills; the
reflective test means a newly-added entity can't silently escape export/erasure (a data-rights bug).

---

## Sources & integration

### D16 — apijobs.dev blocked; 4dayweek deferred
**Decision:** do **not** integrate apijobs.dev (its API host serves a **self-signed TLS cert** —
connecting would require disabling certificate verification, against the egress posture). 4dayweek.io
left documented-only (no canonical `url` field; niche).
**Why:** never weaken TLS verification; keep integrations to clean, verifiable feeds.

---

## Engineering process

### D17 — Fan-out pattern for coupled features
**Decision:** for each feature slice, the **main author writes the coupled backend** (the shared file
+ API contract) first, then **fans out two parallel agents on disjoint files** (frontend in `static/`
+ tests in `tests/`), then **verifies the agent-built UI in the preview**.
**Why:** parallel editing of tightly-coupled code re-creates the "competing definitions" conflict an
early review caught; disjoint-file fan-out is safe and fast. Preview verification by the main author
caught real integration bugs unit tests missed (null-payload 422; an unchecked "right to present"
default excluding every consultant).

### D18 — Adversarial review of security-critical code; verify before reporting
**Decision:** run an adversarial review workflow (find → independently verify each finding before
accepting) on security/correctness-critical code — notably the proposal QA gate — and fix confirmed
findings before shipping.
**Why:** the QA gate is the "never fabricate under the house's name" enforcement; its review found 6
real issues (e.g. an action-verb phrasing bypass) that targeted tests then locked in.
