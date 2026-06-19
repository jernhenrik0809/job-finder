# Proposal Playbook

**For:** a small Danish/EU consulting house bidding for consulting, gig, limited-time project, and public-sector (TED) work.
**Engine context:** v1.34.0 — a local-first pursuit engine that *drafts* a grounded, third-person HOUSE proposal putting forward named bench CONSULTANTS, gated by a fabrication QA check, exported as text today, and **never auto-sent** (a human reviews and submits).

This playbook answers two questions: **what a winning, credible proposal must contain and why**, and **which structured data field fills each part** so the document engine can render it without inventing anything. It is the design reference for the deferred Phase 4 document-generation engine (the build brief lives in `docs/proposal-doc-engine-brief.md`, cross-referenced below).

The single load-bearing idea: **credibility comes from attributable specificity — named people, dated experience, quantified outcomes, real references — and is destroyed by generic, unsupported boilerplate.** That axis maps almost 1:1 onto this codebase's grounding model: every winning signal is something a named `Consultant`'s structured fields can substantiate, and every losing pattern is exactly what `guardrails.check_proposal()` already exists to catch. The structure of the document changes per buying context; the grounding discipline never does.

---

## 1. The principles of a credible bid

A proposal is **not a brochure about the house.** It is a written confirmation of an agreement the buyer can already picture saying yes to. A good proposal "reads like a summary of an agreement you've already reached, not a pitch for business you hope to win" (research, warm-B2B lens).

Six principles, in priority order:

1. **Attributable specificity over adjectives.** Every capability claim must trace to a *specific named person* whose CV supports it. "An experienced team" loses; "Anna Berg, senior data engineer — 6 years building Kafka pipelines, available 1 Aug, 8,500 DKK/day" wins. This *is* the no-fabrication invariant: `unsupported_capability`, `misattributed_skill`, and `no_grounding` are all credibility failures the QA gate already names.
2. **Write for the client's outcome, not your process.** "Clients want outcomes, not inputs — what they'll get beats what you'll do." Over-explaining methodology is a top-five damaging mistake. Lead with what the buyer gets.
3. **Mirror before you pitch.** Open by recapping the client's problem *in their words and numbers* — never introduce new information in the opening. This is the strongest early trust move and it proves you read the brief.
4. **Quantify and name your proof.** Numbers with direction (`-20% cost`, `+30% retention`) and named, reachable references are the highest-trust signals ("92% trust peer recommendations"). Adjectives ("high quality", "proven") are not proof.
5. **Be transparent and bounded on commercials.** State the day rate, the scope (with explicit inclusions *and* exclusions), the assumptions, and the risks-with-mitigations. Maturity reads as credibility; silence on risk reads as naive.
6. **End with one concrete next step.** A specific, dated next action ("a 30-minute scope-alignment call on Thursday") — never "let me know your thoughts." A missing CTA is a top reason proposals languish unsigned. **In this product the human takes that step — the engine never sends.**

> **Why these map to the code.** The credibility engine and the fabrication QA gate are the same thing. The offline template in `proposals.py` already refuses to splice `House.boilerplate` or the client brief verbatim into the QA-checked body, precisely because an unattributable house claim ("deep Kubernetes expertise across our team") can't be tied to a named consultant and would trip the gate on our *own* output. Generic boilerplate doesn't just read badly — it fails the check.

---

## 2. The anatomy — section by section

Each section below states **its job**, **what wins**, **what loses**, and **which structured field fills it.** Entities cited are real: `House` (`jobfinder/house.py`), `Consultant` (`jobfinder/consultants.py`), `Project` / `bench.Project` (`jobfinder/bench.py`), `Opportunity` (`jobfinder/opportunities.py`), and the `ProposalDraft` artifact (`jobfinder/proposals.py`). "Case studies" are flagged as a **gap** — see §2.4.

The default section order below is the full warm/TED form. Gig and staffing replies trim it hard (§4).

### 2.0 Cover / header (branded document only)

- **Job:** Make the document feel accountable and auditable from the first glance — who is proposing, to whom, for what, on what date, under what confidentiality terms.
- **Wins:** A clean cover with proposal title + project title, house logo, client name, date, and a confidentiality/validity line. A running footer with page x-of-y and a signatory/contact block.
- **Loses:** Over-design (multi-color, multi-font, justified text) — reads junior, especially in Denmark.
- **Fields:** `House.name`, `House.tagline`, `House.signatory`, `House.contact`, `House.website`. **Gap:** there is **no logo / color / font / letterhead field on `House` today** — these branded visual assets do not exist in the model and must be captured by the document engine's *calibrate-once* step (`from_dict` tolerates new keys, so `logo_path`, `brand_color`, font paths, etc. can be added without breaking the read path). Project/opportunity title from `Opportunity.title` / `Project.title`; date from `Opportunity.updated`.

### 2.1 Understanding of the engagement

- **Job:** Mirror the client's situation back in their own words/numbers before saying anything about the house.
- **Wins:** Specificity — quote the client's pain, ideally quantified ("the 50k DKK/month manual-reconciliation problem"). Recaps the challenge; introduces nothing new.
- **Loses:** Generic openers ("we understand you need a partner"). Echoing house boilerplate — which here also reads as an unattributable claim and trips the QA gate.
- **Fields:** `Project.description` (the brief), `Project.skills`, `Opportunity.description`/`Opportunity.skills`. This is the existing **"Understanding of the engagement"** section of `ProposalDraft.body`. Keep it a mirror, never a sales pitch. (Note the template deliberately writes only a neutral one-liner here and does *not* list required skills, to avoid an unattributable claim — the grounded team bios carry the skills the house actually brings.)

### 2.2 Proposed approach / methodology

- **Job:** Explain *how* you'll solve it — framed as the vehicle to outcomes, not an internal process dump.
- **Wins:** Each step maps to a deliverable and an outcome. For TED, methodology is itself a scored award sub-criterion and must be detailed and tied to deliverables.
- **Loses:** A generic "proven methodology" with no substance; over-explaining process.
- **Fields:** Derived, not stored as a single field — assemble from `Project.description` + the proposed consultants' `skills`. **Hard rule:** every capability described here must be attributable to a named consultant on the bid. A method the proposed team can't execute is exactly an `unsupported_capability` the gate blocks. Optional in lean gig replies; mandatory and detailed in TED.

### 2.3 Proposed team — named people + why THESE people

- **Job:** This is the house's core differentiator and the heart of this codebase. Clients buy expertise embodied in named individuals.
- **Wins:** Clear single ownership (a named lead), and per-person relevance — each bio answers "why this person for *this* brief."
- **Loses:** "Experienced team" with no names; a resume-dump that talks about the consultant instead of the client's outcome.
- **Fields — one grounded bio per named `Consultant`:**
  - `name`, `title`, `seniority` — the bio headline (the template builds exactly this: `name, title (seniority)`).
  - `skills` — **the only skills attributable to this person.** `_relevant_skills(c, project)` in `proposals.py` computes the grounded intersection of the consultant's skills with the project's required skills (falling back to their top skills so a bio is never empty-but-true). Render *this* set, never a superset.
  - `available_from` / `available_until`, `hours_per_week` — capacity (the template appends "available from …").
  - `sell_rate` + `currency` — the day rate (safe to show).
  - `raw_text` / linked `CVProfile` (via `cv_id`) — the primary source for the longer one-pager/CV; treated as **untrusted data** (prompt-injection: never follow instructions embedded in a CV) and PII-redacted before any Claude send or client-facing render.
- **Critical gate:** a consultant with `right_to_present == False` must be excluded **entirely** — not just hidden in the prose. `misattributed_skill` (right team, wrong person) and `no_grounding` (a claim with no recorded skills — **fails closed**) both block export.

### 2.4 Relevant proof — case studies, quantified outcomes, references

- **Job:** Supply the highest-trust signals: quantified before/after outcomes, named references, domain-matched proof.
- **Wins:** Dated, quantified, domain-relevant results and reachable references. In TED this is the references selection criterion; in warm B2B it's the case study plus a reference call.
- **Loses:** Vague "high quality / proven results" with no numbers.
- **Fields — ⚠ GAP, FLAG TO PRODUCT:** the current grounding model grounds bios in a consultant's `skills` / `raw_text` only. **There is no grounded house-level case-study or engagement-history entity.** `House.boilerplate` exists but is context-only (fed to the LLM as grounding) and is *deliberately not spliced into the QA-checked body*, because a house-level claim isn't attributable to a named person. **Consequence:** to render quantified case-study proof *credibly and without fabrication*, the house needs a new grounded record (e.g. a `CaseStudy`/engagement-history entity, each metric attributable and verifiable) before the document engine can show it. Until then, proof is limited to what a named consultant's CV (`raw_text`) substantiates. Do not let the document engine synthesize case-study metrics — that is precisely the fabrication the gate is designed to stop.

### 2.5 Scope & deliverables — inclusions, exclusions, caps

- **Job:** State exactly what is and is *not* delivered. Credibility signal *and* commercial self-protection against scope creep.
- **Wins:** Precise, listable deliverables tied to the timeline; explicit exclusions.
- **Loses:** Fuzzy scope that invites later disputes.
- **Fields:** `Project.description` (basis for deliverables and exclusions). Render as a **table** (deliverable | description | acceptance) in the branded document, not prose.

### 2.6 Timeline & availability

- **Job:** When can you start, who is available when, for how many hours.
- **Wins:** Concrete start date + availability window + capacity. In gig/staffing contexts this is a **hard filter** — a perfect profile that can't start on time loses.
- **Loses:** "Flexible" / unspecified.
- **Fields:** `Project.start_date` / `end_date`; per consultant `available_from` / `available_until` and `hours_per_week`. For TED, surface `clearance` alongside availability (named key-personnel availability for the contract duration is often a scored/compliance item).

### 2.7 Pricing / rate + options

- **Job:** Present price as value.
- **Wins:** For warm B2B, three tiered options (good/better/best, roughly 1 : 1.6 : 2.5) anchoring the middle tier, each tier mapped to a different outcome/risk profile. For staffing/gig, a single transparent day rate. For TED, price exactly per the tender's price/BPQR scheme. Render as an itemized **table** (role/consultant | day rate | days | line total | total).
- **Loses:** Competing on price alone; mis-pricing; burying or fumbling the number.
- **Fields — HARD RULE:** expose **`sell_rate` + `currency` only.** **NEVER expose `cost_rate`, margin/`total_margin`, `engagement_type`, or `rate_ceiling`.** On the `Opportunity`, `staffed[]` bid lines carry `{consultant_id, consultant_name, cost_rate, sell_rate, currency}` and `_opp_payload` adds per-line and total margin **within one currency** — the margin and cost figures are internal-only and must be omitted by any client-facing render. Keep the price table single-currency (margin totals only compute within one currency).

### 2.8 Assumptions, terms & risk handling

- **Job:** List dependencies, assumptions, payment/cancellation terms, and how key risks are managed.
- **Wins:** Named risks with concrete mitigations; clear commercial terms shorten time-to-signature. For DK/EU, surface `clearance` / `certifications` / consent where relevant (GDPR, work permit, security clearance).
- **Loses:** Silence on risk (reads naive); unsupported guarantees.
- **Fields:** `Consultant.clearance`, `Consultant.certifications`; `Project.required_clearance`; offer-validity and confidentiality lines from the document template. `consent_note` / `data_origin` are **internal provenance — never rendered client-facing.**

### 2.9 Why <House>

- **Job:** Differentiate — grounded, not boilerplate.
- **Wins:** Concrete, attributable differentiators (the senior named consultants on this bid; their specific relevant track record).
- **Loses:** Generic superlatives; verbatim boilerplate (unattributable → trips the gate).
- **Fields:** `House.name`, `House.voice` (steers tone), `House.boilerplate` (LLM grounding *context only*, not spliced into the offline body). This is the existing **"Why <House>"** section of `ProposalDraft.body`.

### 2.10 Next steps / CTA

- **Job:** One concrete, low-friction next step.
- **Wins:** A specific, dated next action (a scheduled review call).
- **Loses:** Passive endings ("let me know").
- **Fields:** the existing **"Next steps"** section; `House.signatory` (falls back to `House.name`) signs off. **Constraint:** the engine never auto-sends — the CTA is for the human-reviewed artifact. `submitted` is a **manual-only** `Opportunity` status; the document must not email, upload to a portal, or otherwise deliver.

---

## 3. Credibility checklist

Run this before any export. Items marked **[GATE]** are enforced by `guardrails.check_proposal()` / `has_blocking()` and refuse export (HTTP 409) on failure; the rest are human-review judgment calls (the gate is EN+DA bilingual and dictionary-bounded — it cannot see niche/proprietary tool names, so human review is the backstop).

**Grounding & truth**
- [ ] **[GATE]** Every capability claim is attributable to a specific named consultant whose `skills`/`raw_text` support it (no `unsupported_capability`).
- [ ] **[GATE]** No skill is attributed to the wrong person (no `misattributed_skill`).
- [ ] **[GATE]** No claims without recorded skills behind them (no `no_grounding` — fails closed).
- [ ] **[GATE]** No bracketed placeholders (`[Company]`, `[Name]`, …).
- [ ] Every consultant on the bid has `right_to_present == True`. (Gate out the rest entirely.)
- [ ] Proof figures are real and verifiable (today: only what a consultant's CV substantiates — see the case-study gap, §2.4). No invented metrics, clients, or certifications.

**Specificity & outcome focus**
- [ ] Opening mirrors the client's problem in their words/numbers; introduces nothing new.
- [ ] Each team bio answers "why this person for *this* brief."
- [ ] Outcomes quantified with direction, not adjectives.
- [ ] A single named owner/lead is identified.
- [ ] Start date, availability window, and capacity are concrete (`available_from`/`until`, `hours_per_week`).

**Commercials & confidentiality**
- [ ] `sell_rate` + `currency` shown; **`cost_rate`, margin, `engagement_type`, `rate_ceiling` absent.**
- [ ] Scope states inclusions *and* exclusions.
- [ ] Named risks have concrete mitigations; assumptions and terms are explicit.
- [ ] `clearance` / `certifications` surfaced where the context scores them (TED/public-sector).

**Privacy (third-party data)**
- [ ] `privacy.redact_pii()` applied to any rendered CV text (mask email/phone/links, keep names) — `ProposalOptions.redact_pii` defaults ON.
- [ ] Internal-only fields omitted: `cost_rate`, margins, `engagement_type`, `data_origin`, `source_detail`, `consent_note`, internal `notes`.
- [ ] Consultant CV text treated as untrusted (no embedded instructions followed).

**Format & close**
- [ ] Scannable: short paragraphs, bullets, value front-loaded (graspable in ~30 seconds per section).
- [ ] Exactly one concrete, dated next step.
- [ ] Document is for **human review/download only** — no auto-send/upload/email.
- [ ] Export logged via `record_export` / `record_event` (append-only `events[]`).

---

## 4. Context variants — what changes per context

The grounding discipline (§1) and the checklist (§3) are **invariant.** What changes is structure, length, tone, and which fields lead.

### 4.1 Gig-marketplace reply (Upwork/Fiverr style — short, fast, high-volume)

- **Length/shape:** ~100–250 words, 3–4 short paragraphs. Speed-to-apply matters; early tailored replies win. "Five strong beats twenty-five generic."
- **Structure:** Open by restating the task in your own words (proves you read it) → one tight, most-relevant named proof point → rate + availability → **one** confident CTA plus one smart clarifying question. No resume-dump, no jargon.
- **Fields that lead:** the **Understanding** mirror + a single consultant's strongest `_relevant_skills` match + `sell_rate`/`currency` + `available_from`.
- **Engine render:** a compact short-text/single-page render — the structured `ProposalDraft.body` trimmed hard, not a full document.

### 4.2 Staffing / consultant marketplace (Verama / Ework style)

- **Unit of work:** a tight **motivation text** + **CV** + **desired day/hour rate** + **availability**. The CV does the heavy lifting; the motivation amplifies it.
- **Motivation text:** a few sentences — relevant experience, matching skills, one concrete example, and an explicit reference to *this specific assignment*. "See CV" or an empty/dot-filled motivation is an **instant loss.**
- **Fields that lead:** render (a) the named consultant's client-facing CV/one-pager from `raw_text`/`CVProfile` (PII-redacted, internal fields omitted), and (b) a short grounded motivation tied to `matched_skills`/`reasons` from `bench.rank_consultants` → `BenchMatch`, plus `sell_rate`+`currency`, `available_from`/`until`, `hours_per_week`. Essentially a one-consultant proposal.

### 4.3 EU public-sector tender (TED — formal, MEAT-scored, compliance-heavy)

Two distinct stages:
1. **Eligibility / selection:** self-declare via **ESPD**; clear **exclusion grounds** (no relevant convictions, tax/social-security compliance, no prior-contract failures); meet **selection criteria** (minimum turnover, insurance, relevant references/capacity). Selection criteria assess the *supplier* and may **not** be reused as award criteria.
2. **Award:** scored on **MEAT / best-price-quality-ratio** — quality sub-criteria (methodology, key-personnel CVs, approach, social/environmental) plus a mandatory price/cost element. In Denmark quality is commonly weighted higher than price (often ~70/30; ~two-thirds of DK tenders use best-price-quality-ratio).

- **What changes:** Long-form, formally structured, follows the **tender's mandated response structure and word caps exactly** (e.g. ~6,000-word work-context answers) — so templates must be **section-addressable**, not fixed. **Key-personnel CVs are scored point-by-point** on *dated per-skill experience* (overlapping projects pro-rated — two parallel full-time roles count ~50% each), required minimum years, and certifications (one missing cert can drop a CV a whole tier). Use the required CV template (often Europass/institutional). **Danish-language output required** (QA cues are already EN+DA). Accessibility is a **hard gate** (see the build brief): tagged PDF/UA-1 + PDF/A, document language set, embedded fonts, tagged tables — a non-compliant PDF can invalidate the bid.
- **Fields that lead:** `Consultant.certifications`, `clearance`, `languages`, `seniority`, dated experience from `raw_text`, `available_from`/`until`, `sell_rate`; `Project.required_clearance`. **The human submits via the portal — no auto-send.**

### 4.4 Direct warm B2B proposal

- **Assumes a prior sales conversation** — reads "like a summary of an agreement you've already reached."
- **Structure:** open with the client's quantified problem and an ROI/business-outcome frame early ("your X investment generates Y") → recap goals (5–7 outcome bullets) and success metrics → approach → named team → proof → scope → timeline → **pricing as three tiered options anchoring the preferred middle tier** → clear terms (dates, payment, cancellation) + signature block → close by **scheduling a review call with the decision-maker** (not "let me know"). Avoid introducing new information that creates confusion.
- **Engine render:** the fullest, most branded render — structured body + team bios + tiered pricing, outcome-led ordering, warm/first-name tone per `House.voice`. Still QA-gated, internal fields omitted, human-sent.

| | Gig reply | Staffing marketplace | TED tender | Warm B2B |
|---|---|---|---|---|
| **Length** | 100–250 words | Motivation + CV | Long-form, capped | Multi-page, branded |
| **Leads with** | Task restatement | Consultant CV | Compliance + scored CVs | Quantified problem + ROI |
| **Pricing** | Single day rate | Desired rate | Per tender's BPQR scheme | 3 tiered options |
| **Tone** | Brief, direct | Concrete, assignment-specific | Formal, factual, DA | Warm, outcome-led |
| **Hard gates** | Speed | Non-empty motivation | ESPD, accessibility, deadline | Prior agreement exists |
| **CTA** | One question + CTA | Rate + availability | Portal submission (human) | Scheduled review call |

---

## 5. What must NEVER appear (ties to the fabrication QA gate)

These are not style preferences — most are **export-blocking** (HTTP 409 via `has_blocking()`) or hard product guarantees. The document engine must inherit every one: it re-runs `guardrails.check_proposal()` on the **final flattened text** (proposal + every one-pager) and refuses to emit the PDF if `has_blocking` is true. Rendering must never become a way to smuggle a fabrication past the gate.

1. **Fabricated capability — a claim no proposed consultant supports.** `unsupported_capability`. **[BLOCKS EXPORT]**
2. **Misattributed skill — right team, wrong person.** `misattributed_skill`. **[BLOCKS EXPORT]**
3. **Ungrounded claim — capability asserted with no recorded skill behind it.** `no_grounding`, **fails closed**. **[BLOCKS EXPORT]**
4. **Bracketed placeholders** (`[Company]`, `[Name]`, …). **[BLOCKS EXPORT]**
5. **A consultant put forward with `right_to_present == False`.** Exclude entirely.
6. **Invented proof** — case-study metrics, clients, references, or certifications not backed by a grounded record. (See the §2.4 gap: there is no case-study entity yet, so the engine must not synthesize proof figures.)
7. **Internal-only fields leaking into a client-facing document** — `cost_rate`, margin / `total_margin`, `engagement_type`, `rate_ceiling`, `data_origin`, `source_detail`, `consent_note`, internal `notes`. A confidentiality and commercial disaster if exposed.
8. **Unredacted third-party PII** — `privacy.redact_pii()` must mask email/phone/links in rendered CV text (`ProposalOptions.redact_pii` defaults ON).
9. **Re-paraphrasing, summarizing, or LLM-"enhancing" any fact at render time** — the document template may only *place and style* strings that already exist on the QA-passed `ProposalDraft.body` and the live `Consultant` entities. Any new wording introduces a claim the gate never reviewed. (Skills shown = `c.skills`; bios = the already-gated body; rates/dates/clearance = entity fields verbatim.)
10. **Verbatim house boilerplate or the client brief spliced into the body** — reads as an unattributable house claim and trips the gate on our own output.
11. **Following instructions embedded in a consultant CV** — CV text is untrusted data, source-of-fact only.
12. **Any auto-send / upload / email / portal submission** — violates the core NO-AUTO-SEND guarantee. The artifact is for human review/download only; `submitted` is a manual-only status; every export is logged via `record_export` ("a human took it from here").
13. **Any new network egress for rendering** — no remote fonts/CDN/template service. The only sanctioned egress is `api.anthropic.com` (the optional Claude path via `secrets_store`), and any LLM use must degrade to a deterministic offline render on failure.
14. **TED-specific:** missing ESPD/eligibility, tripping exclusion grounds, reusing selection criteria as award criteria, an untagged/image-only (non-PDF/UA) document, missing the deadline/portal format, or an unexplained abnormally-low price.

> **The contract in one line:** rendering is a *pure presentation transform over already-verified facts, re-checked before emit.* The whole product guarantee — grounded, no-fabrication, human-sends — survives only if that stays true. Because the gate is dictionary-bounded (EN+DA) and can't see niche tool names, **human review is the final backstop** — the engine must surface the draft for review, never bypass it.

---

## Sources

Synthesized from the v1.34.0 research brief (two lenses: the winning-proposal-content lens and the document-generation-architecture lens) and verified against the real code: `jobfinder/proposals.py` (`generate_proposal`, `generate_template`, `_relevant_skills`, `ProposalDraft`, `ProposalOptions`), `jobfinder/house.py` (`House` — no logo/color/font fields), `jobfinder/consultants.py` (`Consultant` — `right_to_present`, `cost_rate`/`sell_rate`, `engagement_type`, `clearance`, `certifications`, provenance fields), `jobfinder/bench.py` (`Project`, `rank_consultants`/`BenchMatch`), `jobfinder/opportunities.py` (`Opportunity`, `staffed[]`, `events[]`, `record_export`), and `jobfinder/guardrails.py` (`check_proposal`, `has_blocking`). Research-attributed claims (the "reads like an agreement" framing, the ~70/30 DK quality/price weighting, three-tier ~1:1.6:2.5 pricing, the EU Accessibility Act / EN 301 549 / PDF/UA gate, "92% trust peer recommendations", "five strong beats twenty-five generic") are drawn from the supplied research and tagged in-line above.
