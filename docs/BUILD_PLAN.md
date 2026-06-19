# Consulting-House Build Plan

> **Status:** Final plan for owner sign-off. Audience: you (the owner) and whoever implements this.
> **App baseline:** Job finder v1.26.0 — local-first Python/FastAPI + vanilla JS, no telemetry, prepare-and-export only.

---

## 1. Framing & decided guardrails

You already have a working, local, single-seeker job matcher. This plan turns it into a **single-house, single-operator consulting-pursuit tool**: you keep a structured *bench* of consultants and *clients*, an opportunity (warm lead or marketplace posting) gets matched against the bench, and the tool *prepares* a credible, grounded proposal that **a human always submits**. Nothing is sent automatically — ever. The build is sequenced so the highest-value, lowest-risk fix (a confirmed silent-data-loss bug) lands first, the direct-warm channel becomes usable end-to-end before anything fancy, and the polished PDF design engine is explicitly deferred until the rest is in real use.

These guardrails are **decided** and constrain every ticket below:

| Guardrail | What it means in practice |
|---|---|
| **No auto-send, ever** | The engine auto-*generates* proposals + supporting docs; a human submits. No `smtplib`/`imaplib`/`selenium`/`playwright` imports, no `.send_keys(`. `test_no_auto_submit_machinery` and the egress allow-list (`tests/test_security_invariants.py`) stay intact. Output is **prepare-and-EXPORT only**. `api.anthropic.com` remains the only LLM host. |
| **Direct-warm first, both channels covered** | v1 is shaped around manually pasted-in opportunities (email / call / referral) plus a Client/Contact layer — **no scraping needed for warm**. The posting-driven path (Verama-class marketplace replies / EU TED tenders) plugs into the **same** pipeline as a pluggable second mode. |
| **Single-tenant** | Single house, single operator. No auth, no login, no tenancy now. Keep seams clean so a bigger house could run it later, but do **not** build it. |
| **Credibility data now, PDF design later** | Build the credibility **data** layer now (case studies, references, certifications, consultant profiles as structured, *citable* records that ground proposals). The polished, Claude-designed, layout-preserving **PDF production engine is deferred to Phase 4** and is intentionally **not** specced here. |

**Cross-cutting invariants enforced by the test suite (do not break):** the runtime egress allow-list, the no-auto-submit import ban, the literal-host lint, and `test_calibration.py` (the job-seeker scoring must stay byte-for-byte identical). Every new entity must also be wired into `export_all`/`delete_all` or it is a silent GDPR data-rights regression.

---

## 2. Phase-by-phase plan

> **Convention:** `effort` is S/M/L/XL; `risk` is low/medium/high. Ticket summaries are one line — the **id** is the handle for expanding the full spec later. Where the inputs specced the same work multiple times, this plan names **one canonical ticket** and notes the collapse.

### Phase 0 — Gates & foundations

**Goal.** Kill the confirmed silent-data-loss bug, generalize the store's atomic-mutator and data-rights seams, stand up the GDPR consent/retention spine, and unblock the encryption-at-rest decision — without forking the data model. The existing job-seeker app must keep working byte-for-byte.

**Shippable outcome.** Distinct Verama/TED/HackerNews/Freelancer assignments survive de-dup (no more silently dropped opportunities); the operator gets a near-cap storage warning instead of silent eviction; consultant records carry consent/retention metadata with a **flag-only** (non-destructive) expiry sweep; and at-rest encryption ships behind a default-off flag once you pick a key-management option. Calibration + security suites stay green.

| id | title | effort | risk | key files |
|---|---|---|---|---|
| **P0-JOBID-SOURCE-UID** | Add optional `source_uid` to `Job`; prefer it in `Job.id`, else keep legacy `company\|title\|location` hash — fixes Verama/TED/HN/Freelancer de-dup collision | S | low | `sources/base.py`, `sources/verama.py`, `sources/ted.py`, `sources/hackernews.py`, `sources/freelancer.py` |
| **P0-VERAMA-DEDUP-TEST** | Regression test: distinct same-title Verama/TED assignments with different `source_uid` both survive `engine.find_jobs`; identical postings still collapse to one | S | low | `tests/test_engine.py` |
| **P0-STORE-MUTATOR-GENERALIZE** | Extract a reusable atomic read-modify-write `_update_blob` seam in both backends; remove the duplicate `update_saved_search` abstractmethod | S | low | `store/base.py`, `store/sqlite.py`, `store/memory.py` |
| **P0-CONSENT** | Create the canonical `Consultant` record with GDPR `consent_basis`/`consent_at`/`retention_until`; add store CRUD + a **flag-only** expiry sweep in `alerts.py` (notifies, never auto-deletes) | L | medium | `consultants.py`, `store/base.py`, `store/sqlite.py`, `store/memory.py`, `web.py`, `alerts.py` |
| **P0-CAPS-WARN** | Raise bench-safe caps, add `usage()` + `WARN_THRESHOLD`, make eviction logged-not-silent, surface a near-cap warning via `GET /api/storage` | M | medium | `store/base.py`, `store/sqlite.py`, `store/memory.py`, `web.py` |
| **P0-ENC-REST** | **OWNER-GATED.** Pluggable cipher seam at the store boundary + `JOBFINDER_ENCRYPTION` flag (default off); encrypt the `data` blob + `secrets.json`. Implementation waits on the key-management choice (see §3) | L | high | `store/sqlite.py`, `store/__init__.py`, `crypto.py`, `config.py`, `secrets_store.py`, `docs/PRIVACY.md` |

**Phase-0 notes.**
- `P0-JOBID-SOURCE-UID` is the canonical de-dup fix. The inputs specced this bug **five times under four ids** (`P0-VERAMA-DEDUP`, `P0-VERAMA-DEDUP-ID`, `P0-JOBID-SOURCE-UID`, `P2-VERAMA-DEDUP`). Build it **once**, freeze the field name as **`source_uid`** (namespaced by source in the fallback), and alias/delete the rest. The field name propagates into `Opportunity.posting` snapshots, so it cannot change cheaply later.
- `P0-CONSENT` **owns** the `Consultant` dataclass. The Phase-1 consultant ticket may only *extend* it (add fields), never redefine it — otherwise `P0-CONSENT` and `P0-CAPS-WARN` build against a stale shape.
- `P0-ENC-REST` is the only high-risk item and is **droppable from the Phase-0 critical path**: the cipher seam is default-off and nothing in Phase 1 depends on encryption, so a slow key-management decision must not block the warm spine.

---

### Phase 1 — Direct-warm spine

**Goal.** Build the direct-warm channel end-to-end on the unified data model: House identity, the single canonical Consultant entity (extending P0-CONSENT), Client/Contact CRM, the shared bench-match scorer (**one shared TF-IDF space, not `rank_jobs` in a loop**), the eligibility hard-gate (categorically distinct from the never-penalizing nudges), manual paste-in intake, and a prepare-and-export warm proposal flow.

**Shippable outcome.** You paste an email/call/referral lead, see it parsed into an Opportunity, get the bench ranked against it (ineligible consultants dropped to **zero with explicit reasons**, never silently), pick a consultant, generate a grounded proposal from the offline template path, and export it as text for a human to send. A complete warm pursuit loop with zero network egress beyond the optional Claude draft.

| id | title | effort | risk | key files |
|---|---|---|---|---|
| **P1-HOUSE-ENTITY** | Single-row `House` record (name, voice, signatory, boilerplate) stored under a fixed id; grounds every proposal with consistent house voice | M | low | `house.py`, `store/base.py`, `store/sqlite.py`, `store/memory.py` |
| **P1-CONSULTANT-ENTITY** | **Extend** the P0 `Consultant` with commercials (day-rate cost/sell, currency), availability window, certs, clearance, languages, status; store CRUD + cap | M | low | `consultants.py`, `store/base.py`, `store/sqlite.py`, `store/memory.py` |
| **P1-CLIENT-CONTACT-ENTITY** | `Client` aggregate with **embedded** `Contact` list, `do_not_bid` flag, past projects; nested `from_dict` rehydration; store CRUD + cap | M | low | `clients.py`, `store/base.py`, `store/sqlite.py`, `store/memory.py` |
| **P0-BENCH-PROJECT-MODEL** | `Project` (incoming assignment) + a `Consultant` view carrying eligibility/freshness inputs; `project_from_text` for paste-in intake | M | low | `bench.py`, `cv_parser.py` |
| **P1-BENCH-SHARED-VECTOR-SPACE** | Refactor `_tfidf_similarities` into `_tfidf_one_to_many` (zero behaviour change), add `rank_consultants` fitting **one** shared TF-IDF space over project + bench | L | medium | `matcher.py`, `bench.py` |
| **P1-BENCH-ELIGIBILITY-FILTER** | PRE-RANK hard gate (availability / rate-ceiling / clearance) that drops a consultant to score 0 with a disqualifying reason — distinct from `NUDGE_CAP` bonuses | M | medium | `matcher.py`, `bench.py` |
| **P1-BENCH-ENGINE-ENTRYPOINT** | `rank_bench_for_project(project, bench, config)` mirroring `engine.find_jobs`; job-seeker mode untouched | M | medium | `engine.py`, `bench.py` |
| **P1-PASTE-INTAKE** | `POST /api/opportunities/intake`: paste email/RFP → parse → Opportunity → bench match → bid/no-bid suggestion; size-capped, zero egress | L | medium | `web.py`, `intake.py`, `opportunities.py` |
| **P1-WARM-FLOW-DRAFT-EXPORT** | Draft a proposal via `drafts.generate_draft` (template/Claude, guardrails + PII redaction) and export as text via the existing `PlainTextResponse` pattern | M | low | `web.py`, `opportunities.py`, `drafts.py` |

**Phase-1 notes.**
- **Bench-match has two conflicting designs in the inputs.** Build `P1-BENCH-SHARED-VECTOR-SPACE` (one shared TF-IDF fit). Do **not** build the variant that calls `rank_jobs` per consultant in a loop — `matcher.py` builds a fresh vectorizer per call, so per-call cosines are **not comparable across consultants**. Repoint `P1-PASTE-INTAKE` at `rank_consultants` / `P1-BENCH-ENGINE-ENTRYPOINT`.
- The `_tfidf_similarities` refactor **must be pure delegation**. Any diff against the pinned `test_calibration.py` fixture is a hard stop.
- The eligibility gate (hard zero) and the existing nudges (bounded, never-penalizing `NUDGE_CAP=2.5`) are **architecturally separate** — add a code comment so a future contributor doesn't "unify" them.
- `Contact` is **embedded** on the `Client` blob (matches one-blob-per-row, no contacts table/cap). This resolves the conflicting "separate contacts table" spec.

---

### Phase 2 — Proposals + credibility corpus + QA

**Goal.** Generalize the warm flow into a first-class `Opportunity` bid record, land the **one** unified v5 schema migration that registers every new table, build the credibility data layer (case studies / references / certifications / consultant profiles as structured, citable records), fork a house-voice proposal generator, generalize guardrails into a proposal QA-gate whose **blocking** findings prevent export, and add a freshness TTL so stale availability isn't ranked.

**Shippable outcome.** Proposals are grounded in real, attributable credibility records and named-consultant skills. A proposal that invents a client/metric or makes an unattributed capability claim is **BLOCKED from export (HTTP 409 with findings)** until a human fixes it. Stale-availability consultants are surfaced for refresh rather than silently ranked. Export-all / Delete-all stay complete across all new entities.

| id | title | effort | risk | key files |
|---|---|---|---|---|
| **P2-OPPORTUNITY-ENTITY** | Generalize `Application` into `Opportunity` (warm `client_id` OR posting snapshot w/ `source_uid`, staffed consultant ids, economics, bid lifecycle); reuse the event-timeline + validated-status engine; `do_not_bid` clients blocked | L | medium | `opportunities.py`, `applications.py`, `store/base.py`, `store/sqlite.py`, `store/memory.py` |
| **P2-SCHEMA-V5-MIGRATION** | **The single v5 owner.** Bump `_SCHEMA_VERSION` 4→5 once; register house/consultants/clients/opportunities/credibility tables; add the cross-cutting export/delete completeness test | S | low | `store/sqlite.py`, `store/__init__.py` |
| **P1-CORPUS-RECORDS** | `CaseStudy`/`Reference`/`Certification`/`Award` dataclasses; `corpus_for_prompt` (attributable-only) + `citable_index` (real clients/metrics) for the QA gate | M | low | `credibility.py`, `applications.py` |
| **P1-CONSULTANT-PROFILES** | Per-consultant grounding view + `consultant_skill_index` (canonicalized) for per-consultant claim attribution | M | low | `credibility.py`, `skills.py` |
| **P1-CREDIBILITY-STORE** | Persist credibility records + consultant profiles (CRUD, caps); wire into export/delete (table CREATE lines feed the single v5 migration) | M | low | `store/base.py`, `store/sqlite.py`, `store/memory.py` |
| **P0-QA-GATE** | Generalize `guardrails.check_letter` into `check_proposal`: per-consultant attribution, invented-client/metric detection vs the corpus, bilingual (EN+DA regexes), `has_blocking()` | L | medium | `guardrails.py`, `credibility.py` |
| **P0-PROPOSALS-FORK** | `proposals.py` forked from `drafts.py`: third-person house voice, structured sections (scope/team-bios/price tiers), same prompt-cache + `secrets_store` key path + template fallback | L | medium | `proposals.py`, `drafts.py`, `secrets_store.py` |
| **P2-BENCH-FRESHNESS-TTL** | `AVAILABILITY_TTL_DAYS` + `freshness()`; stale consultants suppressed from the ranked list but surfaced in a "needs refresh" list (deterministic via injected `now`) | M | low | `matcher.py`, `bench.py` |
| **P0-EXPORT-BLOCK** | `POST /api/proposals/generate` + export route that runs `check_proposal` and returns **409 + findings** (no artifact) on any blocking finding; JSON/markdown only | M | medium | `web.py`, `proposals.py` |
| **P3-CREDIBILITY-GROUNDING-WIRE** | Feed House voice/boilerplate + staffed consultant profiles + client/past-projects into the grounded drafter as citable reference data; carry source ids for traceability | L | medium | `drafts.py`, `tailor.py`, `web.py` |

**Phase-2 notes.**
- **`Opportunity` is specced twice with different lifecycles.** `P2-OPPORTUNITY-ENTITY` is canonical. Pick one status vocabulary (see §3) before any data exists — renaming is cheap now, expensive later. `submitted` must stay a **manual-only** transition (a human submits).
- **There are four competing "v5" migrations in the inputs.** They cannot coexist: the second to run silently no-ops its `CREATE TABLE IF NOT EXISTS` against an already-v5 DB and its table is missed. `P2-SCHEMA-V5-MIGRATION` is the **single owner** that bumps the version exactly once; every entity ticket contributes only its `CREATE TABLE IF NOT EXISTS` line. This also owns the **export/delete completeness test** that reflects over the table list — the one guard against a silent data-rights regression.

---

### Phase 3 — Posting-driven mode + commercials + UI

**Goal.** Plug the posting-driven path (Verama / TED) into the **same** pipeline as a second mode (no new egress), add commercial relationship tooling (client reminders, house style-examples), and surface everything in the vanilla-JS UI. The posting path stays prepare-and-export only; the sweep notifies, it never auto-submits.

**Shippable outcome.** A gigs saved-search sweep can name best-fit consultants in a notification ("new DK project fits Anna + Lars"); you can rank the bench against a chosen posting; client touch-base / similar-gig reminders flow through the existing notification inbox; and the whole warm + posting + bench + client workflow has a UI. Both channels, one pipeline.

| id | title | effort | risk | key files |
|---|---|---|---|---|
| **P2-BENCH-POSTING-PATH-PLUGGABLE** | `project_from_job(job)` adapter (parse Verama free-text rate, map fields) so a marketplace posting ranks against the bench with zero new fetch logic | M | medium | `bench.py`, `engine.py` |
| **P3-POSTING-PATH** | `job_to_opportunity` + `POST /api/proposals/from-listing`: a selected listing routes into the **same** `generate_proposal` + QA-gate + export path; channel tagged on `Opportunity.source_kind` | M | medium | `proposals.py`, `clients.py`, `web.py` |
| **P2-POSTING-SWEEP-BENCH** | Extend the opt-in `alerts.run_sweep`: for gigs searches, run bench-match on new postings and raise a notification naming top consultants; reuse `AlertScheduler` (no second loop) | L | medium | `alerts.py`, `notifications.py`, `web.py` |
| **P1-CLIENT-VIEW-REMINDERS** | Client/Contact relationship view + touch-base / similar-gig reminders flowing through the existing notification inbox (dedupe-keyed `client:<id>`) | L | medium | `web.py`, `clients.py`, `insights.py`, `alerts.py`, `notifications.py` |
| **P2-HOUSE-EXAMPLES** | Add a `kind` field to examples (`cover_letter`\|`proposal`); proposal path pulls only `kind='proposal'` style examples | S | low | `web.py`, `store/base.py`, `store/sqlite.py`, `proposals.py` |
| **P3-BENCH-UI** | Bench roster management + "staff a project" view (paste-in or pick a posting) reusing the explanation-component renderer; eligibility/stale shown in labeled sections | L | low | `static/index.html`, `static/app.js`, `web.py` |
| **P3-UI-WARM-AND-CLIENTS** | Paste-in intake box, Opportunity board (own tab), Client/Contact relationship view, per-opportunity bench-fit panel | L | low | `static/index.html`, `static/app.js`, `static/style.css` |

**Phase-3 notes.**
- The posting adapter **reuses the frozen `source_uid`** from `P0-JOBID-SOURCE-UID` — it is **not** a new de-dup implementation.
- Default to **notify-only** for high-fit postings (a one-click "promote to opportunity" can come later); auto-creating opportunities risks pipeline spam.

---

### Phase 4 — Deferred document production

**Goal.** OWNER-GATED, internals intentionally **not** specced. The polished, Claude-designed, layout-preserving PDF rebuild (per-house calibrate-once / render-auto, per the PDF-tailoring note) that consumes the Phase 1–3 structured records and drafted proposal text. **Do not begin without explicit go-ahead.**

**Shippable outcome (when eventually scheduled).** Structured `ProposalDraft`s + cited credibility records render to a branded PDF. Until then, export stays plain-text / markdown / JSON. Must remain prepare-and-export only and add no egress beyond `api.anthropic.com`.

| id | title | effort | risk | key files |
|---|---|---|---|---|
| **P4-PDF-DESIGN-ENGINE** | DEFERRED — layout-preserving, Claude-designed proposal/CV PDF production engine; consumes Phase 1–3 records; export-only, no send | XL | high | `jobfinder/` (new module, internals deferred) |

---

## 3. Owner decisions needed

These block or shape the build. The first two gate Phase 0.

1. **Encryption key management (gates `P0-ENC-REST`) — the big one.** Pick one:
   - **A — SQLCipher:** strongest (whole-file, transparent), but a **native dependency + C build toolchain on Windows**, conflicting with the pure-Python ethos.
   - **B — passphrase-derived AES-GCM** at the row-blob seam, using the **already-installed `cryptography`** library: no new dependency, but a passphrase prompt on every start and **forgotten passphrase = unrecoverable data**.
   - **C — OS keyring** random data-key: no prompt, but a new `keyring` dependency, varies headless/Linux, and anyone in the logged-in OS session can read the DB.
   - **Recommendation: B**, with C as a later opt-in. **You must also confirm: is forgotten-passphrase = data-loss acceptable?**
2. **De-dup field name (needed before *any* Phase-0 code):** freeze on **`source_uid`** (recommended) vs `external_id`, and confirm the fallback id stays namespaced by source. This propagates into `Opportunity.posting` snapshots and cannot change cheaply after data exists.
3. **GDPR defaults (`P0-CONSENT`):** default lawful basis (consent vs legitimate_interest), default retention window (12 vs 24 months), and confirm expiry is **flag-only** (manual erasure, no silent auto-delete).
4. **Bench cap numbers (`P0-CAPS-WARN`):** real-bench targets for `MAX_CONSULTANTS` / case-studies / references. `MAX_PROFILES=50` is almost certainly too low once the credibility layer lands.
5. **Consultant record unification owner:** name the single owner so the GDPR / commercials / bench-eligibility / proposal-bio field sets converge into **one** `Consultant` dataclass (P0 owns creation; Phase-1 only extends).
6. **Opportunity status vocabulary:** pick one lifecycle set (e.g. `lead/qualifying/proposal_drafting/proposal_ready/submitted/won/lost/no_bid`) and confirm `submitted` is manual-only.
7. **Eligibility unknown-data posture (`P1-BENCH-ELIGIBILITY-FILTER`):** when availability/rate/clearance is unrecorded — fail-closed or fail-open? (Recommend fail-open for rate/clearance; you pick for availability.) Free-text vs fixed enum for clearance.
8. **Freshness TTL (`P2-BENCH-FRESHNESS-TTL`):** default length (30 days?) and stale = hard-exclude-from-top + refresh list (recommended) vs rank-with-warning-badge.
9. **Posting sources for mode 2:** Verama only, or also TED (different rate semantics / CPV codes — may need its own adapter)?
10. **Credibility entity scope (`P1-CORPUS-RECORDS`):** which records are v1 vs fast-follow (case studies + consultant profiles are highest value); case studies as a separate citable entity (recommended) vs folded into `Client.past_projects`; metrics free-text vs structured `{name,value,unit}`.
11. **QA-gate strictness (`P0-QA-GATE`):** accept the heuristic invented-client/metric scan, or prefer a strict "block any metric not literally in the corpus" policy.
12. **Phase-4 go-ahead:** when to start, and the template/calibration approach. No design decisions needed now.

---

## 4. Build this first

**`P0-JOBID-SOURCE-UID` — the `source_uid`-aware `Job.id` fix.**

This is the single safest, highest-value first increment:

- **It repairs a confirmed, code-verified silent-data-loss bug.** `sources/base.py` `Job.id` hashes only `company|title|location` (lines 30–34). `verama.py` hard-codes `company="Verama"` for every assignment and parses `systemId` only into the URL, discarding it from identity. `engine.py`'s `deduped.setdefault(job.id, job)` then drops the colliding second assignment **with no warning** — verified by repro (two distinct assignments → identical id `d3febf601dd5`; only one survived).
- **It is effort S, risk low, zero dependencies,** and fully backward-compatible: sources that don't set `source_uid` keep their exact legacy md5 id, so the job-seeker app and cross-source de-dup are unchanged and the security + calibration suites stay green.
- **It is a hard prerequisite for everything downstream** — colliding postings would corrupt the Opportunity/staffing/bid records, and the posting-driven second channel can't staff a listing that got silently dropped.

Build it once (covering Verama + TED + HackerNews + Freelancer), immediately lock it with **`P0-VERAMA-DEDUP-TEST`**, collapse the four duplicate de-dup tickets into it, and **freeze the field name as `source_uid`** before any Opportunity or posting ticket depends on the snapshot shape.
