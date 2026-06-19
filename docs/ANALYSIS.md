# Architecture & Business Analysis — Consulting-House Pursuit Engine (v1.33.0)

## 1. Executive summary

You have built something genuinely unusual: a **local-first pursuit engine** that ingests gigs across ~30 sources, matches them against your bench of consultants in one shared scoring space (`bench.py`), drafts a grounded third-person house proposal (`proposals.py`), and refuses to export it if a fabrication gate finds an unsupported capability claim (`guardrails.check_proposal` → HTTP 409 in `web.py:980`). It never auto-sends — a human exports and submits every bid, and that guarantee is enforced by tests (`test_no_auto_submit_machinery`) and a runtime egress allow-list, not by prose.

**Core strength:** *auditable never-fabricate.* Everyone has an LLM. Almost nobody ships a bid tool that can prove a capability claim is attributable to a specific named consultant's real CV, blocks export on fabrication, and keeps an append-only audit trail (`opportunities.record_event`). That is a checked property, and it is your moat.

**Single biggest opportunity:** the product face still points at the wrong user. The code is a consulting-house pursuit engine; the README/VISION/ROADMAP and the default UI still sell an individual job-seeker "career co-pilot," with the entire house pivot grafted into one secondary Bench tab. Re-narrating around the house — and instrumenting the bid→win funnel that already exists at row level — converts a built engine into a sellable product.

**Single biggest risk:** the engine looks correct while being quietly wrong on your highest-value bids. Danish — the language of your best DK/TED gigs — is the matcher's blind spot (`stop_words="english"` at `matcher.py:101`, an English-only skills dictionary), and the bench goes stale silently because `availability_updated` is written by `new_consultant` but never read. Wrong-but-confident "Anna+Lars fit this gig" alerts erode trust in the one feature meant to bring you back daily.

---

## 2. Architecture assessment

**What is right (leave it alone).** The single most important scalability decision is already made correctly: the expensive vectorization runs *outside* the store lock. `bench.py` is a pure module that never touches the store; both the request path (`web.py:933`) and the sweep (`alerts.py:89`) load the bench under a short lock, then score outside it. The migration design — ordered data-backfill steps keyed by target version, separate from the idempotent `CREATE TABLE IF NOT EXISTS` schema (schema v7) — is forward-safe; don't touch it. Atomic read-modify-write mutators (`update_opportunity`, `update_saved_search`) close the lost-update race between the sweep and concurrent edits. The reflective `export_all`/`delete_all` plus its data-rights test mean a new entity can't silently escape erasure.

**The real scale ceilings, in the order they actually bite:**

| Ceiling | Where | Cheapest local-first lift |
|---|---|---|
| **Uncached TF-IDF refit per posting in the sweep** (the first real wall) | `matcher._tfidf_similarities` (matcher.py:101) `fit_transform`s a fresh vectorizer every call; `run_sweep` calls `bench_fit_for_job` inside a per-posting loop. At 100 consultants × 50 new postings = 50 identical fits over 100 full CVs on one daemon thread. | **Hoist the vectorizer out of the loop.** Add `build_bench_index(consultants)` → fit once per sweep, then `transform` only the project text per posting. Collapses S×N fits into ~1 fit + cheap transforms. No new deps. **Effort: M.** |
| **O(n) idempotency scan on the hot ingest path** | `get_opportunity_by_posting` (sqlite.py:289) reads + `json.loads` every opportunity row to find one `(source, source_uid)`. | Maintain an in-memory `{(source,source_uid)→id}` map rebuilt on open, updated on save. O(1) lookup. **Effort: S.** |
| **Global store lock** (the structural ceiling, but not where you break first) | One `threading.Lock` around one shared connection serializes every read/write app-wide. | Justified today — a single operator generates little concurrency, and a `sqlite3` Connection isn't thread-object-safe even under WAL. If it ever bites: a per-thread connection pool (WAL gives file-level concurrency) or a readers-writer lock. **Effort: L. Defer.** |
| **Lexical matcher quality** | TF-IDF cosine, embeddings off by default. | See §5 — this is a quality ceiling, not a throughput one, and enabling embeddings *amplifies* the refit cost unless you fix the sweep first. |

The honest takeaway: the lock is a *documented* ceiling, not the breaking point. Fix the sweep refit and the idempotency scan — both cheap — and the architecture comfortably carries a single house for years.

---

## 3. Security & privacy

**The strong invariants (keep these front-and-centre in any sales conversation):**

- **No-auto-send is verified, not promised.** `test_no_auto_submit_machinery` bans `smtplib`/`imaplib`/`selenium`/`playwright`/`.send_keys`; every export route re-runs `check_proposal` and 409s on a blocking finding (`web.py:980`, `:1139`).
- **Runtime egress allow-list** patches the network layer and records the *actual* host each of ~30 sources contacts, defeating f-string/variable-host evasion. `api.anthropic.com` is the only LLM egress.
- **Clean secret hygiene.** `config.SECRET_FIELDS` is the single source of truth that auto-forces every key into the no-leak sweep; keys resolve env→`secrets.json`→None and never hit the DB or responses (presence booleans only).

**The honest exposures:**

| Exposure | Reality | Proportionate mitigation |
|---|---|---|
| **Plaintext at-rest, now holding third-party PII** | The deferral was sized for *your* CV. The DB now holds real third-party consultant CVs (`consultant.raw_text`) and client PII; WAL/`-shm` sidecars widen the footprint beyond the `.db`. A lost/backed-up/shared laptop is a reportable breach of *non-operator* personal data. | On a solo laptop this is full-disk-encryption's job — **document that as a requirement + add a startup check/warning.** Before any external distribution: encrypt only the high-sensitivity fields (`raw_text`, embedded client contacts) with an OS-keychain/DPAPI key, same owner-only model as `secrets.json`. Add `PRAGMA wal_checkpoint(TRUNCATE)` before VACUUM on `delete_all` so erasure scrubs the sidecars. |
| **GDPR machinery deliberately absent** (your steer) | `consultants.py` keeps only a free-text `consent_note` + one-field `data_origin`, enforced nowhere; `delete_all` is all-or-nothing, so one consultant's "erase me" can't be honored without nuking the install. | Keep skipping consent/retention enforcement. Build the **one operationally load-bearing piece: per-subject erasure** — delete one consultant and cascade-redact their `raw_text` from opportunity snapshots and proposal artifacts. |
| **QA gate mistaken for an oracle** | It's dictionary+cue based (self-documented at `guardrails.py`). A clean result means "no dictionary-matched unsupported claim," not "verified true." A green gate + a 409-on-fail invites over-trust. | At export, render *"No dictionary-matched fabrication found — you are still the reviewer of record,"* and list which claimed skills were verified vs not recognized. Aligns the UI with the code's own honesty. |
| **`redact_pii` asymmetry + `/api/export` CSRF** | Seeker draft/tailor paths default `redact_pii=False` (`web.py:162/170/176`) while proposals default ON; redaction only masks email/phone/URL — names + up to 4000 CV chars still leave the machine. `/api/export` is a GET and same-origin only fires when an `Origin` header is present (`security.py:87`). | Flip seeker defaults to mirror the privacy-first server default; add a redaction self-check on the Claude payload. Require a `Sec-Fetch-Site`/custom-header check on `/api/export` **before** anyone sets `JOBFINDER_ALLOW_LAN`. Low urgency on pure loopback. |

---

## 4. Business & GTM

**Where the value lands.** Your scarcest resource is senior partner time (≈ DKK 1,200–1,800/hr billable). The pipeline attacks three cost centres: discovery (`engine.find_jobs` replaces trawling Verama/TED), triage (`bench.rank_consultants` + `BENCH_FIT_MIN=40` turns "does anyone fit?" into a reasoned, eligibility-gated shortlist — the highest-leverage save, because it's the *judgment* step), and drafting (`proposals.generate_proposal` turns a 60–90 min first draft into a 5–10 min edit). Realistically **1.5–3 partner-hours saved per pursued gig**; across 5–15 gigs/week, a meaningful fraction of an FTE.

**Hours-saved vs win-rate — be honest.** The defensible value today is **hours-saved + more-gigs-pursued** (capacity to bid the long tail you'd otherwise skip), *not* measured win-rate lift. The grounded, QA-gated proposal optimises for not-fabricating, not for winning, and **nothing in the code measures whether it wins more than a hand-written one.** Lead pricing with the provable lever.

**Moat vs commoditisation.** The moat is auditable never-fabricate + your grounded house corpus (your bench's attributable skill graph, which a competitor's identical LLM does not have) + the append-only audit trail as a *client-facing trust artifact* — uniquely sellable into public-sector/TED tenders where attribution matters. Commoditisation pressure ("everyone has an LLM") is countered by selling *provable trust*, not generation.

**Pricing if productised.** Per-proposal pricing is wrong on every axis: it taxes the cheap step (Claude inference is **single-digit DKK/proposal** — `max_tokens=1600`, cached system prefix, CV sliced to 4000 chars — versus tens-to-hundreds of thousands DKK margin on one win, so cost-of-goods never constrains anything), and it penalises the behaviour you want (bidding more). The architecture is single-tenant/single-House (`house.py` `HOUSE_ID`, one global lock, no auth), so per-seat is also a poor fit — one operator per install. **Price a flat per-house annual license,** positioned against partner-hours-saved + win margin.

**The metric to instrument (do this first).** You cannot currently answer *"is this making us win/bid more?"* — `/api/insights` (`web.py:760`) runs `compute_insights` over `list_applications()` only; opportunities are never rolled up, even though the status lifecycle (`won`/`lost`/`no_bid`) and `margin_of` bid lines already exist at row level. Build **`/api/opportunities/insights`**: bids pursued/week, bid→submitted→won conversion, win-rate, total/avg won margin (within-currency only), and `no_bid` count. This is the single biggest economic blind spot and the data is already in the store.

---

## 5. Quality

**One English-only skills dictionary silently gates everything.** `skills.txt` (522 lines, zero Danish terms) feeds the matcher's skills component, the bench (via the shared `_tfidf_similarities`), *and* the fabrication gate (`skill_spans`/`canonical`). One asset's blind spot corrupts three consumers at once — and the blind spot is your highest-value language:

- Danish JDs under-extract skills → false gaps → strong DK consultants mis-ranked downward.
- `stop_words="english"` (matcher.py:101) means Danish stop-words become high-IDF tokens, so EN-CV-vs-DA-brief cosines are systematically low — exactly where you need meaning-aware matching.
- The gate's painstaking Danish possession/verb cues sit on a dictionary with no Danish skill names, so a DA claim about a Danish-named capability is never even spanned — **the gate under-fires precisely in its hardest language.**

**The inert feedback loop is the deepest waste.** `opportunities.py` records `won`/`lost` but nothing feeds those outcomes back into `matcher`/`bench`, and there are no loss-reason fields. You are accumulating the one label-rich dataset a small shop can actually generate — real bid outcomes — and discarding all signal from it.

**Other limits.** Calibration is anchored by only 6 fixture entries and is frozen byte-for-byte (a 6-point fixture can't validate cross-language behaviour). The gate can over-fire `unsupported_capability` on a synonym mismatch and block a *truthful* export (409), tempting bypass pressure.

**Highest-leverage upgrades (ranked):**
1. **Danish layer** — add DA skill/title terms to `skills.txt` mapped to existing canonicals + a combined EN+DA stop-word list (drop `stop_words="english"`). One move lifts bench ranking, fixes false skill-gaps, *and* lets the gate's Danish cues finally span Danish capabilities. **Effort: M.**
2. **Capture structured `loss_reason` + debrief** on the `→lost` transition — pure data capture, no ML, but it converts the inert win/loss record into your only proprietary labeled dataset. **Effort: S.**
3. **Embeddings on the bench path only** (keep `rank_jobs` byte-frozen per `test_calibration.py`) — wire `_semantic_similarities` into `rank_consultants`, calibrate a bench-specific scale. Fixes the cross-DK/EN and synonym cases TF-IDF is structurally worst at. **Effort: M** (only after the sweep refit fix in §2, or the cost ceiling bites hard).

---

## 6. Top potentials (ranked)

| # | Potential | Why it matters | Impact | Effort |
|---|---|---|---|---|
| 1 | **Reframe product around the house** (Bench → primary surface; rewrite README/VISION/ROADMAP) | GTM is impossible while the first artifact a prospect sees contradicts the value; almost all narrative/UI wiring, not engine code | High | M |
| 2 | **Danish-first matcher** (DA skills + stop-words; optional semantic-on-DA) | Lifts your highest-value DK/TED bids across ranking *and* the QA gate simultaneously | High | M |
| 3 | **Opportunity win-funnel endpoint** (`/api/opportunities/insights`) | The instrument that proves ROI and anchors any pricing conversation; data already exists | High | M |
| 4 | **Encrypt bench/client blobs at rest** (OS-keychain/DPAPI field encryption) | Turns the highest-severity latent liability + a procurement deal-blocker into a differentiator | High | L |
| 5 | **Read the `availability_updated` stamp** (soft staleness note, never a hard exclude) | Stops silent stale-bench alerts that quietly destroy trust in the daily hook | High | S |
| 6 | **Hoist bench vectorizer out of the per-posting sweep loop** | First real CPU wall as the bench grows; invisible until it stalls | High | M |
| 7 | **Capture `loss_reason` + proposal edit-distance** | The only proprietary labels a small house can generate + a measured hours-saved proxy | High | S/M |
| 8 | **Signed desktop installer** (PyInstaller + pywebview) | The gate to any buyer who won't run Python | High | L |
| 9 | **Per-subject erasure** (delete one consultant + cascade-redact artifacts) | The one operationally load-bearing GDPR piece for a house holding sub-consultant CVs | High | M |
| 10 | **Stop silently evicting consultants/opportunities** (`_evict` → explicit archive/hard-fail) | These now hold durable third-party CVs + bid audit trails, not disposable search results | Medium | S |
| 11 | **Index the posting-idempotency lookup** (in-memory `(source,source_uid)→id`) | Removes the only O(n) locked scan on the hot ingest path | Medium | S |
| 12 | **Bench bulk-import** (folder/zip multi-CV ingest) | Crushes B2B cold-start; value only appears after the corpus exists | Medium | S |

---

## 7. Prioritized roadmap

**NOW — make the engine trustworthy and provable on the data you already have.**
- **Read `availability_updated`** (`bench._eligibility`): emit a soft "last confirmed N days ago" note + show it on every `BenchMatch` and bench-fit notification. The fail-open steer is preserved — note, never disqualify. *(potential #5)*
- **Danish matcher layer** (`skills.txt` + `matcher.py:101` stop-words). *(potential #2)*
- **`/api/opportunities/insights`** over `list_opportunities()`. *(potential #3)*
- **Capture `loss_reason`** on the `→lost` transition in `opportunities.py`. *(potential #7)*
- **Hoist the sweep vectorizer** + index the idempotency lookup (`alerts.run_sweep`, `sqlite.get_opportunity_by_posting`). *(#6, #11)*
- **Convert `_evict` on `consultants`/`opportunities`** from silent delete to explicit archive/hard-fail. *(#10)*

**NEXT — make it sellable to a second house.**
- **Reframe the product** (Bench-first UI + rewritten README/VISION/ROADMAP). *(#1)*
- **Field-level encryption at rest** for `raw_text` + client PII; `wal_checkpoint(TRUNCATE)` before VACUUM. *(#4)*
- **Per-subject erasure** cascade. *(#9)*
- **Bench bulk-import** + surface `MAX_CONSULTANTS` eviction explicitly. *(#12)*
- **Signed desktop installer.** *(#8)*
- **QA-gate honesty in the UI** + flip `redact_pii` seeker defaults + harden `/api/export` before any LAN bind.

**LATER — earn the right with usage data first.**
- **Embeddings on the bench path** (after the sweep refit fix; calibrate a bench-specific scale; keep `rank_jobs` frozen). *(§5 #3)*
- **Win/loss-weighted tuning of `BENCH_FIT_MIN`** once `loss_reason` + outcomes have accumulated.
- **Richer skill ontology** (relations beyond flat aliases) — only after the Danish layer + outcome capture show where the real gaps are; risks loosening gate precision.
- **Read/write lock or connection pool** — only if a real concurrency ceiling ever materialises.

**What stays deferred — and the trigger that flips it:**
- **Encryption-at-rest (full-DB):** stays deferred *only* while this is a solo-laptop install on an encrypted volume. **Trigger to act: the moment the box is shared, backed up off-device, or a second house touches it — or `data_origin=third_party` rows accumulate with empty `consent_note`.** Until then: full-disk-encryption requirement documented + startup warning. Note this is a *deferred-but-required* commitment, not a permanent waiver.
- **Phase-4 PDF tailoring engine (Claude-designed, layout-preserving):** stays owner-gated and unbuilt. **Trigger: a paying second house exists** and proposal *presentation* (not generation correctness) becomes the bottleneck on win-rate. It is downstream of GTM and instrumentation — building it before you can measure win-rate is gold-plating.

---

## 8. The 3 things most likely to make it fail in practice

1. **Confidently-wrong bench-fit alerts on a stale, English-blind bench.** `availability_updated` is written and never read; `_eligibility` fails open on the *common* blank availability window (`project_from_job` never sets dates); and Danish — your highest-value bids — degrades TF-IDF toward noise. The alerts *look* curated (the `BENCH_FIT_MIN` floor implies vetting), so you trust them, until a real bid puts a departed or unavailable consultant forward. The daily hook becomes a noise source and you stop opening it. **This is the most likely failure and the cheapest to prevent** (read the stamp; add Danish).

2. **The narrative/packaging gap strands the pivot.** The code is a pursuit engine; the product face is a CV-matcher run from `start.bat`. A non-technical boutique owner sees a job-seeker tool, can't install Python, and churns before reaching the value — and the gap signals the pivot was never a deliberate product decision, undermining roadmap credibility. Without the reframe + installer, there is no buyer beyond you.

3. **No proof it works, so the ROI story is anecdote.** Win/loss outcomes are recorded and never aggregated; win-rate lift is asserted and unmeasured; loss-reasons are discarded. If the grounded house voice reads generic and loses competitive bids, the only real value reverts to hours-saved — and you won't *see* it happening, because the funnel that would tell you isn't instrumented. A "nice toy" that quietly fails to convert, with no dashboard to catch it, is how this dies slowly.