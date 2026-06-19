# Build Brief — Proposal Document-Generation Engine (deferred Phase 4)

**Addressed to:** a fresh "Claude design" session with **no memory of the conversation that produced this brief.** Everything you need to start cold is here. Read it top to bottom before writing code.

**Companion docs (read these next):**
- [`docs/proposal-playbook.md`](./proposal-playbook.md) — the *anatomy* of a winning proposal (what each section is for, what wins/loses, and **which structured field fills it**). This brief tells you what to BUILD; the playbook tells you what each rendered section must CONTAIN. Cited below as "playbook §N".
- [`docs/examples/`](./examples/) — the sample consulting house you will render against (§6).

**Product context:** `jobfinder` is a **local-first consulting-house pursuit engine** (v1.34.0). It already *drafts* a grounded, third-person **HOUSE** proposal that puts forward named bench **CONSULTANTS**, gated by a fabrication QA check, exports the proposal as **plain text** today, and **never auto-sends** — a human always reviews and submits. The house bids mostly for **Danish/EU** consulting, gig, and limited-time project work, **including public-sector TED tenders.**

---

## 1. Goal + where it fits

**Build the document-GENERATION engine: the deferred Phase 4 that replaces/augments the text export step.** It consumes the already-QA-passed structured proposal plus the live entities and emits a **branded, client-ready PDF proposal** plus **consultant one-pager / CV documents** — for a human to review and send.

### What already exists (do NOT rebuild)
- **Drafting:** `jobfinder/proposals.py` → `generate_proposal(house, project, consultants, options, examples)` returns a `ProposalDraft` (structured `subject` / `body` / `consultant_ids` / `consultant_names` / `generator` / `note`). The `body` is plain text with named sections: greeting → `Understanding of the engagement` → `Proposed team` (one grounded bio per named consultant) → `Why <House>` → `Next steps`. It has two backends — an offline deterministic **template** and an optional **Claude** path — and always falls back to the template on any error.
- **The fabrication QA gate:** `jobfinder/guardrails.py` → `check_proposal(body, consultants)` returns findings; `has_blocking(findings)` is `True` if any must block export. This is the load-bearing safety contract — see §4.
- **Entities:** `House` (`jobfinder/house.py`), `Consultant` (`jobfinder/consultants.py`), `Project` (`jobfinder/bench.py`), `Opportunity` (`jobfinder/opportunities.py`).
- **Export today (what you are replacing/extending):** two text-export endpoints in `jobfinder/web.py`:
  - `/api/proposals/export` → `export_proposal_endpoint` (around line 982)
  - `/api/opportunities/{oid}/export` → `export_opportunity_proposal` (around line 1141)

  Both already: strip the body → load the proposed consultants (`_load_consultants` / `_opp_consultants`) → re-run `check_proposal` → **refuse with HTTP 409 if `has_blocking`** → build a `.txt` `PlainTextResponse` with a `Content-Disposition` attachment filename. The opportunity path also calls `record_export` for the audit event.

### Where your engine plugs in
**After the existing `has_blocking` check passes**, instead of (or alongside) building the `.txt` response, call your engine with `(house, subject, body, [Consultant, ...])` and return a **PDF** (and optional one-pager PDFs). The opportunity path must keep calling `record_export`. The engine reads the **live entities** for branding / bios / rates / availability / clearance — it does **not** re-parse the text `body` for data. The entities are the source of truth; the QA-passed `body` is the source of *prose*.

**Boundary:** export-only. The engine produces a local file artifact for human review/download. **It never emails, uploads to a tender portal, or otherwise delivers to a client.** A human takes it from there.

---

## 2. The document set to produce + required sections

Two document kinds. Reference **playbook §2** ("the anatomy — section by section") for the job/wins/loses and the exact source field of every section listed below.

### 2A. The branded PROPOSAL document (one PDF per proposal)
The primary deliverable. Lays out and brands the QA-passed `ProposalDraft.body` over the house identity. Required sections (playbook §2.0–§2.10):

| Section | Source of content | Playbook |
|---|---|---|
| **Cover / header** — proposal title, project title, client/recipient, date, confidentiality + validity line; running footer with page x-of-y + signatory/contact | `House.name`/`tagline`/`signatory`/`contact`/`website`; title from `Opportunity.title`/`Project.title`; date from `Opportunity.updated` | §2.0 |
| **Understanding of the engagement** | the existing section of `ProposalDraft.body` | §2.1 |
| **Proposed approach / methodology** | the body (when present) | §2.2 |
| **Proposed team** — one grounded bio per named consultant | the `Proposed team` section of the body, one block per `consultant_ids` entry | §2.3 |
| **Relevant proof** — ⚠ see §2.4 gap below | only what a consultant's CV substantiates today | §2.4 |
| **Scope & deliverables** — render as a table when present | from the body | §2.5 |
| **Timeline & availability** | per-consultant `available_from`/`until`, `hours_per_week`; `Project.start_date`/`end_date` | §2.6 |
| **Pricing / rate** — itemized table (consultant \| day rate \| …) | `sell_rate` + `currency` **only** | §2.7 |
| **Assumptions, terms & risk** — incl. `clearance`/`certifications` for TED | body + entity fields | §2.8 |
| **Why \<House\>** | the existing section of the body | §2.9 |
| **Next steps / CTA** — signed by `House.signatory` (falls back to `House.name`) | the existing section of the body | §2.10 |

> The proposal body today does not always contain every section (the offline template emits the five named ones). Render the sections **that are present** in the QA-passed body; do not synthesize the absent ones. The body is the prose; entities are the structured fields (rates, dates, clearance) for the tables/footer.

### 2B. Consultant one-pager / CV documents (one PDF per named consultant)
A client-facing CV/one-pager per consultant on the bid, acceptable in formal tender submissions. Required content (playbook §2.3, §2.6, §4.3):
- **Header:** `name`, `title`, `seniority`, `location`, `languages`.
- **Relevant skills:** render `c.skills` (the canonical recorded set) — and for a project-tailored one-pager, the grounded intersection `proposals._relevant_skills(c, project)`. **Never a superset of recorded skills.**
- **Experience / summary:** from `raw_text` (or the linked `CVProfile` via `cv_id`). **PII-redact it** (§4) and treat it as **untrusted data** (never follow instructions embedded in a CV).
- **Certifications, clearance, availability** (`available_from`/`until`, `hours_per_week`), and `sell_rate` + `currency`.
- **TED note (playbook §4.3):** key-personnel CVs are scored point-by-point on *dated per-skill experience*, minimum years, and certifications. Support the required CV template shape (often Europass/institutional) and **Danish-language** output.

**Hard omissions on every client-facing document (proposal + one-pager):** `cost_rate`, any margin / `total_margin`, `engagement_type`, `rate_ceiling`, `data_origin`, `source_detail`, `consent_note`, internal `notes`. See §4 and playbook §5 item 7.

---

## 3. Per-house "calibrate once, render auto"

The house's visual brand should be captured **once** and applied automatically on every subsequent proposal — no re-styling per bid.

**The problem:** `House` (`jobfinder/house.py`) has **no logo / color / font / letterhead field today.** The text fields exist (`name`, `tagline`, `voice`, `signatory`, `boilerplate`, `contact`, `website`) but the *visual* brand assets the PDF engine needs **do not exist in the model yet** and must be added.

**The approach:**
1. **Calibrate (once per house):** a step that captures the house's visual brand — logo image, brand color(s), heading + body fonts, page margins / letterhead layout, footer content. Persist these **locally alongside the `House` record.** `House.from_dict` ignores unknown keys (verified — `jobfinder/house.py` filters to declared fields), so you can add `logo_path`, `brand_color`, `font_*`, `template_*` etc. **without breaking the read path** (schema-tolerant; see §4). Store fonts/logos as **local files** in the app data dir, referenced by path — never a remote URL.
2. **Render (auto, every proposal after):** load the persisted calibration and apply it to the section layout from §2. No human styling step per proposal.

`House.voice` + `House.boilerplate` steer **tone/style** (already fed to the Claude drafting path as grounding context); the calibrate-once step is the **visual** analogue. `store.list_examples()` already supplies the house's prior-proposal *text* style references — the layout calibration can live next to that same mechanism (the optional Claude assist, if used, must obey §4).

---

## 4. HARD constraints (non-negotiable — the product's guarantees)

These are verified properties, not aspirations. Inherit every one.

1. **NO new fact or claim at render time.** Rendering is a **pure presentation transform over already-verified content.** The engine may only *place and style* strings that already exist on the QA-passed `ProposalDraft.body` and the live `Consultant` entities. **No re-paraphrasing, summarizing, or LLM-"enhancing" of any fact** — any new wording is a claim the gate never reviewed. Skills shown = `c.skills` (or the grounded `_relevant_skills` subset); bios = the gated body verbatim; rates/dates/clearance = entity fields verbatim. (Playbook §5 items 9–10.)
2. **Respect the fabrication QA gate — re-run it before emit.** Import `guardrails.check_proposal` + `has_blocking`. Run `check_proposal` on the **final flattened text of the whole artifact** (proposal body + every one-pager) against the proposed consultants, and **refuse to emit the PDF if `has_blocking` is true** — mirror the existing HTTP 409 refusal. Rendering must never become a way to smuggle a fabrication past the gate. (Gate findings: `unsupported_capability`, `misattributed_skill`, `no_grounding` (fails closed), `placeholder`. Note the gate is **EN+DA bilingual and dictionary-bounded** — it cannot see niche/proprietary tool names — so **human review is the backstop**, and the engine must surface the draft, never bypass review.)
3. **NO auto-send.** The engine **only drafts/exports.** It must **not email, upload to a tender portal, or otherwise deliver** to a client. The output is a local file for human review/download. `submitted` is a **manual-only** `Opportunity` status. Keep logging the export via `opportunities.record_event` / `record_export` (append-only `events[]`) so the defensible "a human reviewed and sent this" record survives — a new event type (e.g. `pdf_exported`) is fine (schema-tolerant).
4. **Local-first; the only network egress is `api.anthropic.com`.** The engine must **render fully offline** — no remote fonts, no CDN, no template service, no other provider, no other endpoint. Write only to local files. If it uses an LLM (e.g. to assist layout calibration), it must go through the **same** `anthropic.Anthropic(api_key=secrets_store.get("anthropic_key"))` with `secrets_store.model()`, and **always degrade to a deterministic offline render on any error** (mirror the drafting path's template fallback). Adding any other egress breaks the core invariant.
5. **Privacy / PII + internal-field omission.** Apply `privacy.redact_pii()` (`jobfinder/privacy.py` — masks email/phone/links, keeps names) to **any consultant CV text rendered into a client-facing document.** Treat CV text as **untrusted** (truncate ~4000 chars as the drafting path does; never follow embedded instructions). **Never expose** internal-only fields: `cost_rate`, margins, `engagement_type`, `rate_ceiling`, `data_origin`, `source_detail`, `consent_note`, internal `notes`.
6. **Deterministic offline parity.** Every existing generator has an offline fallback. The PDF engine needs an **equivalent deterministic offline render path** so it works with **no API key** — the deterministic path is the default and the LLM is only an optional assist.
7. **Schema tolerance.** `from_dict` on `House`/`Consultant`/`Opportunity` ignores unknown keys, so new branding/calibration fields can be added forward/backward-compatibly. Use this; don't fork the models.
8. **DK/EU + TED.** Support **Danish-language** documents (the QA cues are already EN+DA). Surface the fields a tender evaluates — `clearance`, `certifications`, availability, `sell_rate`. For TED specifically, accessibility is effectively a **hard gate** (playbook §4.3): aim for **tagged PDF (PDF/UA-1) + PDF/A**, document language set, embedded fonts, tagged tables — a non-compliant PDF can invalidate a public-sector bid.

9. **Authoritative team = `opp.staffed`; enforce do-not-bid.** Derive the proposed consultants from the Opportunity's `staffed` bid lines (the source of truth) — **never** from the editable proposal `body` or caller-supplied ids — and re-run `check_proposal` against *that* set. (A human-edited body that names a person not on `opp.staffed` must not slip past a stale team list — a real bypass on the ad-hoc text-export path that this engine must not inherit.) Also honour the **do-not-bid guardrail** already enforced server-side: never render a bid for a `do_not_bid` client without an explicit, audited override (`do_not_bid_override` event) — see `_block_do_not_bid` in `web.py`.

> ⚠ **Proof / case-study gap (playbook §2.4 — flag, do not work around):** the grounding model substantiates bios from a consultant's `skills`/`raw_text` only. There is **no grounded house-level case-study / engagement-history entity**, and `House.boilerplate` is deliberately context-only (not spliced into the QA-checked body). So quantified, attributable house-level proof has **no source the engine can render without fabricating.** Render only what a named consultant's CV substantiates; **do not synthesize case-study metrics, clients, references, or certifications.** A new attributable `CaseStudy` record is needed before a proof section can show house-level metrics — that is out of scope here.

---

## 5. Suggested tech approach + tradeoffs (do not over-prescribe)

The constraints above (pure-Python, fully local, deterministic offline default, embeddable/taggable PDF) are firm; the *how* is your call. A reasonable starting point and its tradeoffs:

- **HTML/CSS → PDF (recommended default).** Render each document from a templated HTML+CSS layout, then convert to PDF locally. This keeps the calibrate-once brand assets as plain CSS variables (color/fonts/margins) + an `<img>` logo, makes the per-house template legible and tweakable, and makes Danish/Unicode + tables straightforward.
  - **WeasyPrint** — pure-ish Python, good CSS support (incl. paged-media headers/footers, page x-of-y), runs fully offline, embeds local fonts. Tradeoff: PDF/UA tagging + PDF/A conformance is partial — verify against the §4.8 accessibility target and consider a post-process for TED.
  - **Tradeoff vs. a direct PDF library** (e.g. ReportLab): direct layout gives precise control and solid PDF/A support but is far more code for multi-section branded layouts and tables; HTML/CSS is faster to build and to recalibrate per house.
  - **Avoid:** any converter that needs a network call, a remote font/CDN, a headless-browser download at runtime, or a hosted template service — that would break the single-egress invariant (§4.4). Bundle fonts locally.
- **Layout calibration assist (optional):** Claude *may* help translate a brand sample into a CSS theme — but only via the sanctioned `secrets_store` Anthropic client, and the deterministic offline theme must be the fallback (§4.6). The LLM must never touch the *facts* — only layout/style.
- **One template, section-addressable.** TED requires following a mandated response structure and word caps (playbook §4.3), so make the template **section-addressable** rather than one fixed monolith — sections can be reordered/omitted per context variant (gig vs. staffing vs. TED vs. warm B2B; playbook §4).

Pick the smallest stack that satisfies §4. Justify the PDF library choice against the accessibility target in a short note.

---

## 6. Example inputs to render against

Sample **fictional** consulting house, already in the repo under [`docs/examples/`](./examples/) (created alongside this brief). Mirrors the real entity shapes so you can load it directly.

| File | Contents |
|---|---|
| [`docs/examples/house.json`](./examples/house.json) | **Nordlys Consulting** — house identity: `name`, `tagline`, Danish-tone `voice`, `signatory` ("Søren Dahl, Partner"), `boilerplate`, `contact`, `website`. (No logo/color/font yet — your calibrate-once step adds them.) |
| [`docs/examples/consultants.json`](./examples/consultants.json) | three bench consultants — **Anna Berg** (Senior Cloud & Data Engineer), **Lars Holm** (Solution Architect, .NET/Azure), **Mette Nielsen** (Data Scientist / ML) — each with `skills`, `languages`, availability, `certifications`, `clearance`, day rates in **DKK**, and a full CV in `raw_text`. Note each also carries internal-only fields (`cost_rate`, `engagement_type`, `consent_note`, …) you must **omit** from client-facing output. |
| [`docs/examples/opportunity.json`](./examples/opportunity.json) | a sample gig — **"Cloud migration & data platform — Danish fintech"** (source: Verama; `rate_ceiling` 1200 DKK; `start_date` 2026-08-01) with staffed bid lines (Anna + Mette) and a **ready, QA-passing** `proposal_body`. |

Load them with the real models:
```python
import json
from jobfinder.house import House
from jobfinder.consultants import Consultant
from jobfinder.opportunities import Opportunity

house = House.from_dict(json.load(open("docs/examples/house.json")))
cons  = [Consultant.from_dict(c) for c in json.load(open("docs/examples/consultants.json"))]
opp   = Opportunity.from_dict(json.load(open("docs/examples/opportunity.json")))
proposed = [c for c in cons if c.id in {l["consultant_id"] for l in opp.staffed}]  # Anna + Mette
```
`opportunity.json.proposal_body` is grounded **only** in Anna's and Mette's real CVs and **passes the gate with no blocking findings** today — render it faithfully; do **not** add claims at render time.

**Expected example output:** a branded, client-ready **proposal PDF** for Nordlys Consulting (Danish business tone, single-currency DKK price table showing `sell_rate` only) **plus one-pager CVs for Anna and Mette** (PII-redacted, internal fields omitted).

---

## 7. Acceptance criteria + how to verify

The engine is done when all of the following hold for the §6 example (and the general path):

1. **Renders a credible PDF.** Running the engine on the example produces a branded proposal PDF + one-pager PDFs for Anna and Mette that open in a standard reader and look like a credible Danish consulting bid (cover, sections from §2, footer with page x-of-y + signatory).
   - *Verify:* render, open the PDFs, eyeball against playbook §2/§4 (no over-design — playbook §2.0).
2. **Rendered facts match the source — nothing added.** Every capability/skill/rate/date/clearance in the PDFs traces to the QA-passed `proposal_body` or a live `Consultant` field. No paraphrasing, no invented proof.
   - *Verify:* diff the rendered text against `opp.proposal_body` + entity fields; confirm skills shown ⊆ `c.skills`, rates = `sell_rate`, and **none** of `cost_rate`/margin/`engagement_type`/`rate_ceiling`/`data_origin`/`source_detail`/`consent_note`/internal `notes` appear anywhere in the PDFs (extract text and assert absence).
3. **Passes the QA gate at emit.** The engine re-runs `check_proposal` on the final flattened artifact text and only emits when `not has_blocking`; a blocking finding refuses emission (HTTP 409 on the endpoint path).
   - *Verify (the source already passes):*
     ```python
     from jobfinder.guardrails import check_proposal, has_blocking
     assert not has_blocking(check_proposal(opp.proposal_body, proposed))   # passes today
     ```
     Then assert the engine **refuses** when fed a deliberately fabricated body (e.g. attribute a skill to Anna she lacks) — emission must be blocked, not silently rendered.
4. **No new egress.** The full render path runs with **no API key set** and **no network access** — no remote fonts/CDN/portal/provider beyond the optional `api.anthropic.com` assist, which must degrade to the deterministic offline render on failure.
   - *Verify:* run with `ANTHROPIC_API_KEY` unset and outbound network blocked; confirm a complete deterministic PDF still renders. Confirm the only outbound call anywhere in the engine (if any) is the `secrets_store` Anthropic client.
5. **Privacy + audit.** CV text in client-facing PDFs is run through `privacy.redact_pii()` (no raw email/phone/links; names kept). The opportunity export path still calls `record_export` and appends an audit event.
   - *Verify:* the example one-pagers show "[email redacted]"/"[link redacted]" style masks (if the CV had any) and full names; the opportunity's `events[]` gains an export entry.
6. **Calibrate-once works.** A house's brand assets are captured once (persisted via schema-tolerant `House` fields / local files) and applied automatically to a second, different proposal render without re-styling.
   - *Verify:* calibrate Nordlys once, render two different proposals, confirm both pick up the same logo/colors/fonts with no extra input.

7. **Accessibility VERIFIED, not just targeted (TED path).** "Eyeball the PDF" cannot detect a missing structure tree or an unset document language. Add a programmatic conformance check — veraPDF (PDF/UA-1 + PDF/A) or, at minimum, assert a tagged structure tree + a declared `/Lang` + embedded fonts + tagged tables — that **blocks or loudly warns** before a TED submission, with a matching automated check. A non-conformant PDF can invalidate a public-sector bid (playbook §4.3, §5.14).
   - *Verify:* run the conformance check on the rendered TED-path PDF and assert it passes (or is loudly flagged); a deliberately untagged render must fail the check.

> **Deferred build decisions to spec when you build (not blockers for a first render):** artifact versioning/identity (content hash + generator + QA-finding-set + team snapshot + language in the export `meta`), retention/encryption of superseded PDFs (inherits the at-rest commitment if retained), bundling the proposal + one-pagers into one submission pack (merged PDF/zip), a DRAFT/CONFIDENTIAL watermark until approved, a signature block, **output language beyond Danish/English**, embedded-font licensing, byte-stability/determinism, and large-bench render performance (cap one-pager `raw_text` ~4000 chars as the drafting path does). A `CaseStudy` entity and `House` branding fields (logo/colour/font) are prerequisites flagged in §3 and the playbook §2.4/§2.0.

**Definition of done:** the §6 example renders into a credible, brand-consistent PDF set; rendered facts match the source exactly; the QA gate re-runs against the authoritative `opp.staffed` team and blocks fabrication before emit; the do-not-bid guardrail holds; the path runs fully offline with no new egress; no auto-send; export is audit-logged. Wire it in behind the existing `has_blocking` check in `export_proposal_endpoint` / `export_opportunity_proposal` (`jobfinder/web.py`), preserving the 409 refusal and `record_export`.
