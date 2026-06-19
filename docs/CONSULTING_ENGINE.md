# Consulting-House Pursuit Engine — overview

How the local job-matcher was extended into an engine that finds project/gig postings, matches them
against a **bench** of consultants, and drafts grounded **proposals** a human reviews and sends.
Built across **v1.26.1 → v1.33.0** (Phases 0–3). The full plan is in [BUILD_PLAN.md](BUILD_PLAN.md);
the reasoning behind the choices is in [DECISIONS.md](DECISIONS.md); the architecture/business review
is in [ANALYSIS.md](ANALYSIS.md).

> **Core principle:** the engine *drafts and exports* — it **never auto-sends**. A human exports and
> submits every proposal. Enforced by `tests/test_security_invariants.py` (no-auto-submit import ban +
> runtime egress allow-list). See [DECISIONS.md](DECISIONS.md) D1.

---

## The end-to-end loop

```
ingest postings            match the bench           draft + verify            track + decide
(~30 sources, gig-focused) (one shared TF-IDF        (house-voice proposal,    (Opportunity +
        │                   space + hard              grounded; QA gate          audit trail;
        ▼                   eligibility gate)         blocks fabrication)        bid/no-bid)
  engine.find_jobs  ──►  bench.rank_consultants ──► proposals.generate_proposal ──► opportunities.*
        │                       │                    + guardrails.check_proposal        │
        │                       ▼                            │                          ▼
        │                bid/no-bid (BENCH_FIT_MIN)          ▼                   human exports & SENDS
        │                       │                    POST /api/proposals/export   (audit: "exported")
        ▼                       ▼                    or /opportunities/{id}/export
  background sweep ──► "this new gig fits Anna + Lars" bench-fit notification (🎯)
  (alerts.run_sweep)
```

**Two channels, one pipeline:**
- **Posting-driven (primary):** the background sweep bench-matches each new posting and raises a
  bench-fit notification; the operator opens the Bench tab, ranks/staffs, drafts a proposal, exports.
- **Direct-warm (secondary):** paste a brief in the staff form, or track a relationship in the
  Client/Contact CRM; the same match → propose → export pipeline applies.

---

## Data model (new entities)

All are JSON-blob-per-row dataclasses (`to_dict`/`from_dict` drop-unknown-keys), persisted on both
`MemoryStore` and `SqliteStore` (schema **v7**), wired into `export_all`/`delete_all` (a reflective
test enforces coverage), each capped.

| Entity | Module | Purpose | Key fields |
|---|---|---|---|
| **Consultant** | `consultants.py` | a bench member | skills, seniority, languages, availability window, `cost_rate`/`sell_rate`/`currency`, `engagement_type`, `right_to_present`, `data_origin` (provenance), `clearance`, `status`, `cv_id`→profile |
| **House** | `house.py` | single-row house identity | name, voice, signatory, boilerplate (grounds proposal voice) |
| **Opportunity** | `opportunities.py` | a pursued project (the bid record) | project snapshot, `source`+`source_uid` (idempotency), `staffed` bid lines (consultant + cost/sell/currency), lifecycle status, proposal artifact + last QA, **append-only `events`** (audit trail) |
| **Client** | `clients.py` | direct-warm account | sector, embedded contacts, `do_not_bid`, past projects |

`Project` (`bench.py`) is the transient "thing to staff", adapted from an ingested `Job`
(`project_from_job`) or a pasted brief.

---

## Matching & proposal quality

- **Bench matcher** (`bench.rank_consultants`): scores many consultants against one project in **one
  shared TF-IDF space** (so cross-consultant scores are comparable), reusing the existing
  `matcher._tfidf_similarities`. A **pre-rank eligibility gate** zeroes an ineligible consultant
  (inactive / not-presentable / unavailable for the window / over a same-currency rate ceiling) with
  an explicit reason — categorically separate from `matcher.py`'s never-penalizing nudges. Fails
  **open** on unknown data; never compares rates across currencies.
- **Bid/no-bid** (`bench.qualify_fits`, `BENCH_FIT_MIN=40`): only surface a gig when an eligible
  consultant clears the "good match" band — the volume control.
- **Proposal generator** (`proposals.generate_proposal`): third-person **house voice** (author = the
  house, subjects = the proposed consultants), grounded **only** on the chosen consultants' real CVs +
  the house identity. Offline **template** path (grounds bios only in skills a consultant actually has)
  + optional **Claude** path that falls back to the template on error. Redaction defaults to the
  server's privacy setting.
- **Fabrication QA gate** (`guardrails.check_proposal` + `has_blocking`): flags a capability claimed
  for **no** proposed consultant (`unsupported_capability`), **misattributed** to the wrong named one,
  unverifiable on a **thin corpus** (`no_grounding`, fail-closed), or a placeholder — in **English and
  Danish**. Export **re-runs** it and refuses with **409** on any blocking finding. It is a
  high-precision **assist, not an oracle** (dictionary + cue based) — the real guarantee is human review.

---

## API surface (consulting engine)

| Area | Endpoints |
|---|---|
| **Bench** | `POST/GET /api/consultants`, `GET/PATCH/DELETE /api/consultants/{id}` |
| **House** | `GET/POST /api/house` |
| **Staffing** | `POST /api/bench/rank` (gig → ranked bench with eligibility + reasons) |
| **Proposals (ad-hoc)** | `POST /api/proposals/generate`, `POST /api/proposals/export` (409 on blocking) |
| **Opportunities** | `POST/GET /api/opportunities`, `GET/PATCH/DELETE /api/opportunities/{id}`, `POST /api/opportunities/{id}/proposal`, `GET /api/opportunities/{id}/export` |
| **Clients** | `POST/GET /api/clients`, `GET/PATCH/DELETE /api/clients/{id}` |
| **Automation** | the opt-in sweep (`alerts.run_sweep`) raises `bench_fit` notifications; `POST /api/alerts/run-now` |

UI: a **Bench tab** with sub-sections — Consultants, House, Staff-a-gig, Pipeline (opportunities +
audit trail + margin), and Clients.

---

## What shipped, by phase

| Phase | Version(s) | What |
|---|---|---|
| **0 — foundations** | v1.26.1 | `source_uid` de-dup fix; store/migration groundwork |
| **1 — bench spine** | v1.27.0 – v1.29.0 | Consultant/House entities + store; the bench-inverted matcher + eligibility gate; web wiring + Bench UI |
| **2 — proposals** | v1.30.0 – v1.31.0 | proposal generator + fabrication QA gate; Opportunity entity + append-only audit trail |
| **3 — automation & CRM** | v1.32.0 – v1.33.0 | posting-sweep → bench-fit notifications + bid/no-bid; Client/Contact CRM + margin surfacing |
| **4 — deferred** | — | Claude-designed layout-preserving PDF proposal/CV engine — **owner-gated, not built** |

**366 tests**, CI green across Python 3.12 + 3.13. Each slice was built backend-first by the main
author, fanned out to parallel frontend + test agents on disjoint files, and preview-verified; the
security-critical QA gate also went through an adversarial review (see [DECISIONS.md](DECISIONS.md)
D17–D18).
