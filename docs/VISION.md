# Job Finder — Target-State Vision

*Living design document — last updated 2026-06-10. Drafted via a multi-agent design pass and a completeness review; see the **Addendum** at the end for review corrections that supersede the body where they conflict.*


## North-star

> **Your private career co-pilot: turn one CV into a ranked shortlist of real jobs and review-ready applications — entirely on your own machine, no account, no surveillance.**

Job Finder is the **local-first matcher-and-drafter** for the individual job seeker who wants honest signal and tailored output without handing their job search to a platform. It answers the two questions incumbents answer badly: *"Of the live jobs out there, which am I actually a strong match for — and why?"* and *"Can I get a tailored, review-ready application for each, in my own voice, without auto-spamming anyone?"* — and it does so on the user's PC, free by default, with every paid/online capability an explicit opt-in.

The center of gravity moves from a **one-shot session tool** (upload → search → draft → close, all lost on restart) to a **persistent, returning-user campaign companion**: durable saved searches that surface what's *new*, a real apply→track→follow-up pipeline, transferable-skill matching as the default moat, and honest gap-coaching — all inside an encrypted, telemetry-free, review-first fence.

---

## Personas & Jobs-to-be-Done

| Persona | Pain | Job-to-be-done | What the product owes them |
|---|---|---|---|
| **Active seeker** (primary) | Volume + repetition + losing the thread across 5 boards; applying 10–40 roles/week | A daily ranked shortlist and fast, personalized drafts; know what I sent and what's next | Pipeline/tracking, saved searches, follow-up nudges, fast ethical apply-handoff |
| **Passive / curious** (secondary) | Won't broadcast intent on LinkedIn (boss sees it) or hand a CV to a cloud tool | A quiet weekly digest of genuinely strong matches | Local-first privacy as the killer feature; opt-in background "career watch" |
| **Career-switcher** | Literal title doesn't match target roles; keyword search buries them | Honest transferable-skill matching + a real gap analysis, not flattery | Semantic/taxonomy matching, "roles you wouldn't have searched for", upskilling report |
| **New-grad / early-career** | Thin CV, high anxiety, no budget for Teal/Simplify | Free, offline drafting that reads as competent + "what should I learn" coaching | Encouraging gap-coaching framing, zero-key core, voice-matched template letters |

### The journey we own (end-to-end, within the ethical fence)

**Discover → Match → Tailor → Apply → Track → Follow-up → Land.** We own each stage only where a local-first tool can ethically and reliably add value:

- **Discover** — multi-source aggregation (free APIs + keyed aggregators + employer ATS + RSS), de-duped, *never mass-scraped*.
- **Match** — explainable 0–100 score with matched/missing skills; the core moat, evolving to semantic + transferable-skill.
- **Tailor** — offline template by default; optional Claude grounded strictly in the real CV; expands to resume tailoring + screening-Q&A.
- **Apply** — review-first Outbox + one-click *handoff* (open the real page, copy the pack). **We assist; we never auto-submit.**
- **Track** — persistent pipeline (saved→applied→interview→offer) with reminders, all user-driven.
- **Follow-up** — reminder-triggered follow-up drafts reusing the drafting engine.
- **Land** — Vision-tier interview prep from JD+CV and offer comparison.

---

## Product Principles

1. **Local-first, private by architecture.** No account, no telemetry, no cloud store. Any data leaving the machine (a search query, an optional API call) is explicit, minimal, and user-initiated. Enforced by a CI test that fails on any non-allow-listed outbound host (allow-list = the job sources the user picked + `api.anthropic.com`).
2. **Offline-capable by default; paid is additive, never gating.** Template drafts, parsing, lexical+taxonomy scoring, and the in-app inbox all work with zero keys. Claude, JSearch/Adzuna, and embeddings are opt-in upgrades the user controls via their own key — the core never degrades to a paywall.
3. **Honest over flattering.** Absolute (not curved) scoring, visible-but-encouraging missing-skills coaching, drafts that never fabricate experience. A grounding verifier makes "no fabrication" a *checked property*, not a prompt's hope.
4. **Review-first, human-in-the-loop.** We draft, stage, and hand off. There is no `submit()` anywhere in the architecture — by design, and guarded by a CI test that fails if any SMTP/Selenium/form-post dependency is imported.
5. **Ethical sourcing.** Public, no-login endpoints at personal volume, with a shared politeness layer (rate caps, backoff, global per-run ceiling) that makes mass-scraping impossible by construction. Tiered consent: official/free-API sources on by default; guest/gray (LinkedIn) opt-in with a one-time disclaimer.
6. **Runnable by a non-technical person.** One double-click to a working app — ultimately a signed installer with no Python or terminal. Optionality is progressive; power features never block the first run.
7. **Explainable and inspectable.** Every score decomposes into components and human-readable reasons; the skills graph and config are inspectable files; drafts show their generator; the user can always understand, override, export, and shred.

### Explicit Non-Goals

- **Not an auto-apply / mass-application bot** — never auto-submit, bulk-apply, or fill external forms without the user driving each submission.
- **Not a cloud SaaS / multi-tenant platform** — no hosted multi-user service, no server-side storage of user CVs. (A *self-hosted* shared variant is a Vision divergence, never a hosted product we operate on users' data.)
- **Not a social/professional network, recruiter/ATS product, or credential vault.** Candidate-side, single seeker, single machine; we never store job-board passwords.
- **Not a guaranteed-coverage index** — we aggregate accessible public sources honestly; we don't promise to scrape every career page.
- **Not a résumé-fabrication tool** — we tailor truthful CVs via user-approved diffs with provenance; we never invent experience to game a match.

---

## Target Architecture

The single structural weakness today is that **`web.py` is simultaneously the web layer, the data layer (three module-global dicts: `_PROFILES`, `_EXAMPLES`, `_DRAFTS`), and the wiring layer**, with a hardcoded `if name == "linkedin"` source dispatch and scattered `os.environ.get` reads. Everything works, but extension means editing core files and a restart wipes every CV, draft, and example. The target introduces four seams — a real plugin system, a repository layer over an *encrypted* SQLite store, a thin service layer, and an opt-in in-process scheduler — while keeping the thing that makes Job Finder good: **one command, one process, fully offline by default.**

```
┌────────────────────────────────────────────────────────────────────────┐
│  PRESENTATION                                                            │
│   jobfinder/api/  thin FastAPI routers (validate → call service → map)   │
│     routes_cv  routes_search  routes_drafts  routes_apps  routes_alerts  │
│     routes_plugins  routes_data   deps.py (DI: app.state.container)      │
│   jobfinder/static/  vanilla-JS shell: Home · Search · Tracker · Outbox  │
│                      · Insights · Settings  (left nav rail, theming, a11y)│
│   Network boundary: 127.0.0.1 default; TrustedHost + same-origin CORS;   │
│     --allow-lan + session token required for non-loopback bind           │
└───────────────┬──────────────────────────────────────────────────────────┘
                │ UI never imports a plugin or repo
┌───────────────▼──────────────────────────────────────────────────────────┐
│  SERVICE LAYER  jobfinder/services/   (pure Python, no FastAPI imports)   │
│   cv_service        parse + persist profile                              │
│   search_service    orchestrate sources → match → rank → persist + cache │
│   draft_service     generate (template|llm) → guardrail verify → Outbox  │
│   tailor_service    resume reorder/rewrite with provenance map           │
│   app_service       application lifecycle state machine + events         │
│   alert_service     saved searches + run-on-schedule + diff/notify       │
│   feedback_service  log signals → bounded logistic re-weighter           │
└──────┬───────────────────────┬───────────────────────┬───────────────────┘
       │                       │                       │
┌──────▼────────┐   ┌──────────▼──────────┐   ┌────────▼──────────────────┐
│ PLUGIN REGISTRY│   │ REPOSITORY LAYER    │   │ SCHEDULER (opt-in)        │
│ plugins/       │   │ store/              │   │ jobs/scheduler.py         │
│  protocols.py  │   │  base.py (Protocols)│   │  1 worker thread via      │
│  registry.py   │   │  memory_repo.py     │   │  FastAPI lifespan;        │
│  entry_points  │   │  sqlite_repo.py     │   │  run_due_searches()       │
│  + @register   │   │  migrations.py      │   │  + reminder sweep         │
└──────┬─────────┘   └──────────┬──────────┘   └───────────────────────────┘
       │                        │
┌──────▼─────────────────┐  ┌───▼───────────────────────────────────────────┐
│ PLUGINS (capabilities) │  │ PERSISTENCE  %LOCALAPPDATA%\JobFinder\          │
│  sources/  linkedin …  │  │  jobfinder.db — SQLite (stdlib sqlite3, WAL)    │
│  matchers/ tfidf semant.│ │  ENCRYPTED-AT-REST: AES-GCM on raw_text/draft   │
│  generators/ tmpl claude│ │  body/example text; key wrapped via OS keystore │
│  (no submit() exists)  │  │  (DPAPI/Keychain/libsecret); file ACL owner-only│
└────────────────────────┘  │  + fetch_cache (gzipped raw source responses)   │
                            └────────────────────────────────────────────────┘

CONFIG & SECRETS  jobfinder/config.py
  Settings (pydantic-settings, SecretStr) ← env → ~/.jobfinder/config.toml → defaults
  The ONLY module that reads secrets. Keys never persist to the DB or any API response.
```

**Arrows point only downward.** The UI never imports a plugin; a service never imports FastAPI; a plugin never imports a repository; the Outbox has no send path. Every capability below is *additive and absent-by-default* — a fresh install behaves exactly like today, plus durable encrypted storage.

| Concern | Default (zero-config, offline) | Opt-in bolt-on | Never required |
|---|---|---|---|
| Storage | Encrypted SQLite in app-data dir | `memory` mode (ephemeral) | external DB |
| Sources | Remotive, Arbeitnow (no key) | Adzuna/Jooble/JSearch (key), ATS, RSS, LinkedIn (consent) | account/login |
| Matching | TF-IDF + taxonomy skill graph | semantic (MiniLM), cross-encoder, LLM re-rank | GPU/cloud |
| Drafting | template + Voice Profile + lang tables | Claude / local Ollama | always-on AI |
| Alerts | off | in-process scheduler → in-app inbox | Redis/Celery |
| Worker | none (single process) | OS-scheduled CLI (`python -m jobfinder.jobs.run_alerts`) | message broker |
| Notifications | in-app bell | desktop toast, user's own SMTP digest | our servers |

### The plugin system (the headline structural change)

Three concerns are conceptually pluggable but only `sources` pretends to be, and even that is a hardcoded dispatch. Unify **sources, matchers, generators** under one discovery mechanism using stdlib `importlib.metadata.entry_points` + `typing.Protocol` + a `@register` decorator — no plugin framework, ~120 lines. Each capability declares a `PluginManifest` (`id`, `kind`, `label`, `requires_key`, `optional_deps`, `ethical_note`, `tos_tier`). The registry **filters to only what will actually work**, so the UI stops offering sources/generators that fail at runtime (today `/api/sources` lists `jsearch` with no key, then it errors at search time) and explains why others are greyed out. Crucially, **no plugin protocol exposes `submit()` or mass-scrape** — third-party plugins inherit the ethical guardrails by construction.

---

## Data Model

One embedded **SQLite** file (stdlib `sqlite3`, WAL, FK on) at an OS-appropriate per-user path (`%LOCALAPPDATA%\JobFinder\` on Windows), overridable via `JOBFINDER_DATA_DIR`, created and migrated on first launch via a hand-rolled forward-only `schema_version` migration runner (no ORM, no Alembic). Sensitive columns are encrypted at rest. The **`memory_repo`** (today's dicts, lifted verbatim) stays as a swappable backend for tests and the privacy-paranoid ephemeral mode.

```
Profile (the candidate; usually one, multiple CV versions supported)
  └─1:N─ CVDocument        raw_text + profile_json + sha256 content_hash (re-upload dedups)
SavedSearch (reusable query) ─1:N─ SearchRun ─M:N─ Job (via JobSighting; new_job_count powers "N new")
Company (deduped by name_key) ─1:N─ Job ; ─1:N─ Contact
Job (the dedup anchor) ─1:N─ Match (Job×CVDocument, matcher_version) ; ─1:N─ Application
Application (the promoted unit of retention; was "Draft")
  └─1:N─ Draft (versioned cover-letter/resume artifacts; is_current)
  └─1:N─ Reminder (follow-up nudges)
  └─1:N─ Event (immutable per-application timeline)
Example (LLM voice references) ; FetchCache (gzipped raw responses, TTL'd)
Event (append-only log) ; Setting (retention policy, defaults, key-presence flags)
```

**Two model shifts unlock the whole vision.** First, **`Job` becomes the dedup anchor**: a posting seen on LinkedIn *and* Adzuna is one `Job` row with two `JobSighting` rows, replacing the brittle `md5(company|title|location)` id with a **layered key** — prefer a normalized canonical-URL key, fall back to `sha256(company_name_key | title_norm | location_norm)`. Dedup **never drops a job**, only merges links (`also_seen_on`), so the user never loses a lead and can apply via the employer's ATS front door. Second, **`Application` is promoted above `Draft`**: an application is the durable pipeline item (status `saved → drafting → ready → applied → screening → interview → offer → rejected/withdrawn`); a draft is one versioned artifact under it. This is what turns the Outbox from a draft buffer into a campaign tracker.

**Data control is a first-class surface:** backup = copy one file (`VACUUM INTO` snapshot); portable export/import (`jobfinder-export.zip` with human-readable `data.json`, dedup-merging on import); per-application `.txt`/`.md`/`.pdf` and pipeline CSV; typed-confirm wipe with **crypto-shred** (destroy the wrapping key for hard-delete); and a retention TTL that auto-prunes stale jobs/cache. No telemetry, ever.

---

## End-to-End Journey (target)

1. **Onboard** — drop a CV (or "use a sample CV"); it parses from an **in-memory `BytesIO`** (killing today's `tempfile(delete=False)` plaintext leak at `cv_parser.py:50`) into a persisted, encrypted `CVDocument`. Skills extract against a bundled ESCO/O*NET-derived **skills graph** (canonical/aliases/broader/narrower/related), not a flat list.
2. **Discover** — pre-filled keywords/location from the profile, free sources pre-selected. `search_service` fans out across selected source plugins (cached + rate-limited via shared `FetchContext`), normalizes `RawJob → Job` centrally, dedups with provenance.
3. **Match** — a **recall → precision → personalization funnel**: always-on offline Stage A (TF-IDF + taxonomy-aware skill overlap with partial credit + title + structured seniority/salary/location/recency signals), optional local embeddings (Stage B), optional top-K LLM re-rank (Stage C), and a bounded ±15pt on-device personalization re-weighter (Stage D). Every job carries a **calibrated explanation object** (score + confidence + component bars + top reasons), not a bare float.
4. **Triage** — Save to pipeline (a `saved` Application), Hide/Not-interested (remembered across re-runs), or select for drafting.
5. **Tailor** — generate cover letter (template+Voice Profile offline, or Claude grounded strictly in the CV), optionally a **provenance-mapped tailored resume** and screening answers from a fill-once **Answer Profile**. A **guardrail verifier** blocks placeholders and flags any claimed hard-skill absent from the CV before a draft can be marked ready.
6. **Apply** — review/edit in the Outbox; one-click ethical handoff opens the real posting and copies the Application Pack. The human presses submit.
7. **Track** — drag the card across the Kanban pipeline; each transition logs an immutable event; entering `applied` auto-schedules a +7-day follow-up reminder; terminal states stop all nudges.
8. **Return** — saved searches re-run on cadence (≥6h rate-limited), surfacing only what's *new* in an in-app inbox; the Insights funnel turns the multi-week campaign into motivation and tactics.

---

## Capability Areas

### Sources & Coverage
Shift the center of gravity off the fragile LinkedIn guest scrape toward **Adzuna (free keyed, global, salary data) + employer ATS direct (Greenhouse/Lever/Ashby, the most ethical full-description source) + free no-key APIs**. A declarative `SourceMeta` + `Query`/`FetchContext`/`RawJob` contract collapses the repeated 5-positional `search()` signatures, centralizes the three duplicated `_strip_html` helpers into one normalization pass, and lets the engine plan queries by capability. A shared `requests-cache` SQLite HTTP layer with per-source TTLs (LinkedIn descriptions 7d — they're immutable — removing most 429 pressure) makes re-search instant and polite. A `healthcheck()` + live source-status picker replaces silent empty results.

### Matching Intelligence
The bundled **skills graph** is the highest-leverage change: it fixes false "missing skill" chips (a candidate with scikit-learn no longer told they're "missing" machine learning), reduces keyword-pedigree bias via transferable-skill partial credit, and feeds the **upskilling report** ("Learning Kubernetes appears in 14 of your 20 matches and would move 6 jobs above 70"). Promote the unused `salary` field and seniority/location to scored, explainable, never-penalizing signals. Calibrate the 0–100 against a CI fixture set so the number means something. Learn locally and modestly — a transparent, bounded, bubble-resistant logistic re-weighter over implicit (drafted/applied) + explicit (thumbs) signals that never leaves disk.

### Drafting & Tailoring
Keep the clean two-backend shape (template offline + Claude grounded), widen the scope: **resume tailoring with a provenance map** (every output line traces to a CV source line — what makes it safe rather than a fabrication engine), **screening-Q&A** (factual answers come *only* from the Answer Profile, never the LLM), **multi-language** (EN/DE/FR/ES/NL tables offline, full fluency with key), and a **Voice Profile** distilled from examples so even offline letters feel personal. Job descriptions are treated as untrusted input (delimited against prompt injection). The ethical boundary — drafting into a review-first Outbox, never auto-submit — is the product's contract, not a backlog item.

### Application Tracker (the retention core)
Persistence turns Job Finder from a session tool into a 4–12 week campaign companion: a Kanban Pipeline (the new home of the Outbox tab), per-application timeline/notes/contacts drawer, a local rule-based reminder engine (offline asyncio lifespan scheduler + startup catch-up sweep), saved-search alerts, and an Insights funnel (saved→applied→interview→offer with conversion %, response rate, time-to-response, response-by-source/score-band). All transitions are user-driven; nothing is scraped from inboxes; terminal states stop nudges so the tool never nags about a dead lead.

### UX & Distribution
A keyboard-first nav shell (left rail, command palette, `j/k/d/s` feed nav), dark/light/system theming, WCAG 2.1 AA accessibility (ARIA on the score donut, live-region search status), a first-class **Settings** page so non-coders paste API keys instead of touching env vars, and a skippable 3-step onboarding. Distribution ladders from a hardened `pyproject.toml` console-script, to the **headline non-coder deliverable — a signed PyInstaller + pywebview desktop app** (`JobFinder-Setup.exe`/`.dmg`/`.AppImage`) reusing the entire FastAPI stack untouched, to an optional Docker/compose for self-hosters. An opt-in LAN toggle (with QR) makes phone access real without exposing a port by default.

### Trust, Privacy & Quality
The invariants every feature must preserve: **no CV byte leaves the device** except a typed search query or (opt-in) the CV+job to Anthropic; **no auto-submit/authenticated-scrape/credential-harvest, ever**; **at-rest data encrypted and crypto-shreddable**. Backed by mechanically-enforced CI contracts (no-secret-in-response, no-auto-submit-import, no-unexpected-outbound-host), a Windows CI matrix with ruff/mypy/coverage≥85%/pip-audit gates, recorded-fixture source tests so LinkedIn HTML drift is a caught failure not a silent zero-results bug, point-of-action disclosure banners, and the policy docs (LICENSE, PRIVACY.md, ETHICS.md, SECURITY.md) that turn the ethical stance from convention into contract.

---

## Addendum — Design-Review Corrections & Risk Gaps

A completeness review of the vision above surfaced four internal contradictions, several under-scoped risk surfaces, and some scope discipline. **Where this addendum conflicts with the body above, the resolutions here win.**

### A. Corrections (resolve contradictions in the body)

1. **The default source must be free/official, not LinkedIn.** Today `engine.py` defaults `SearchSettings.sources = ['linkedin']`, which silently opts the user into the grayest source — contradicting the "free/official on by default, LinkedIn opt-in behind a one-time disclaimer" principle. **Resolution:** default to `['remotive','arbeitnow']`; LinkedIn is opt-in only.
2. **Backup vs. encryption — two explicit modes.** An OS-keystore-wrapped key means a raw file copy is *not* a portable backup. (a) **Local snapshot** (`VACUUM INTO`) — restorable only on the *same* OS user + machine. (b) **Portable backup** — requires a user **passphrase-derived key** (export/escrow), or the JSON export (plaintext, user-initiated, clearly labelled). "Copy one file" is only a same-machine snapshot, never a cross-machine backup.
3. **The CI egress allow-list is two mechanisms, not one.** *CI-time* allow-list = the static union of **all registerable source hosts** + `api.anthropic.com`. *Runtime* guard = the **per-user selected** sources + `api.anthropic.com` (only when a key is set). Both must be specified; the CI test uses the static union.
4. **The "0 plaintext CVs on disk" KPI is scoped** to *at-rest application storage*, explicitly **excluding user-initiated exports** (the JSON export necessarily contains plaintext by the user's own action).

### B. Risk surfaces to add to the Trust & Reliability posture

- **LLM egress — the one real egress — needs a data-handling disclosure.** The optional Claude path sends the full CV (up to ~8 000 chars) + the job description to `api.anthropic.com`. Add: (a) an explicit in-app disclosure of *what is sent, to whom, and retention*; (b) a link to Anthropic's data-use / zero-data-retention terms; (c) an optional **"redact PII (name, email, phone, address) before sending"** toggle; (d) a first-use per-send confirmation.
- **Key-loss / recovery is the most likely real data-loss event.** OS-keystore-wrapped keys (DPAPI / Keychain / libsecret) are tied to the OS account and die on reinstall/account change → silent total loss of the user's pipeline. Ship a setup-time **recovery option (passphrase-derived key export / printable recovery code)** in the *same unit of work* as encryption, plus a "recover from passphrase" flow.
- **Failure & empty states (the reliability persona).** Design for the dominant real path, not just the happy one: zero results, source HTML drift, 429s mid-search, near-empty parse from a scanned PDF (`looks_empty()` already detects this). Define a graceful-degradation narrative, per-source health/status surfacing, and a **search-success / non-empty-result rate** design budget.
- **Third-party plugin abuse breaks "impossible by construction."** Once third-party source plugins run in-process, a plugin's `search()` can scrape, ignore rate caps, harvest credentials, or call arbitrary hosts — the Protocol cannot stop that. Mitigations: a **vetted first-party registry**; the shared politeness layer enforced by the *host*, not the plugin; per-plugin capability/host **allow-list declaration**; a blunt "third-party plugins run with full trust — install only what you trust" warning; sandboxing as a Vision-tier research item. Do **not** open the plugin SDK before at least capability-allowlisting exists.
- **CV-parse quality is a first-class risk, not a detail.** Every downstream score and draft inherits parse errors; non-English / Europass / two-column / graphic-designer PDFs parse poorly. Add a **"confirm & edit your parsed profile"** step in onboarding now (cheap, no persistence, large trust + accuracy lift); NER + layout handling later.
- **UI i18n / a11y / RTL scope.** Drafting is multi-language but the UI chrome, RTL, and non-Latin CV parsing are unaddressed. Stated scope: English UI first; chrome i18n + RTL as a tracked **Later** item if EU adoption warrants.
- **SQLite single-writer concurrency.** The opt-in scheduler thread writes concurrently with foreground UI writes on one SQLite file. Specify: **WAL + `busy_timeout`**, a single-writer queue/lock, and that long alert sweeps yield to user writes.
- **Model tier & cost.** `drafts.py` hardcodes `claude-opus-4-8`; a batch of up to 20 jobs at Opus is a real, undisclosed cost on the user's own key, and model IDs deprecate. Add a **model-tier setting** (Haiku / Sonnet / Opus), a **per-run cost preview**, and a model-deprecation update path.
- **Bundled-data / model licensing.** The skills graph bundles ESCO (CC-BY) + O*NET (own terms); the installer bundles MiniLM (Apache-2.0) + PyInstaller'd dependencies. A generated **NOTICE / third-party-licenses** file and in-app attribution are a **release prerequisite**, not an afterthought.

### C. Scope discipline

- **Demote Postgres multi-device sync** from a Vision bet to *"researched & rejected unless strictly single-tenant self-host"* — a Postgres-backed sync server is the exact architecture the north-star defines against.
- **Gate the multi-stage ML ranker** (MiniLM bi-encoder → cross-encoder → learned re-weighter → per-user calibration) on a **measured win against the calibration fixture set**, not as scheduled work. The offline TF-IDF + taxonomy core is the promise ("runs on any laptop, no download"); each ML stage stays strictly optional and must beat the fixtures to earn its place.
- **Unmeasurable KPIs:** telemetry-free means field metrics (e.g. *time-to-first-match*) can't be measured in production — reframe them as **design budgets validated in CI / manual QA**, not field KPIs.

### D. Decisions needed (open questions for the product owner)

1. **Encryption dependency:** accept an OS-keystore lib (`keyring`) + SQLCipher/app-layer AES-GCM as a required default, or keep the default pure-stdlib with encryption opt-in? (Changes the threat model and the "copied DB is useless elsewhere" guarantee.)
2. **Keep or retire LinkedIn** in v1.5+ once Adzuna + ATS coverage lands? (Ongoing breakage/reputational cost vs. perceived coverage.)
3. **Code-signing budget/ownership** for the desktop installer (Windows Authenticode + Apple notarization, ~hundreds/yr), or ship unsigned and accept SmartScreen/Gatekeeper friction for the exact non-technical audience?
4. **Alerts cadence model:** app-open catch-up sweep only, an OS-scheduled CLI tier, or a true always-on "career watch" daemon (and defer alerts until then)? A seeker's PC is often off/asleep.
5. **Skills-graph bundle ceiling:** acceptable repo/installer size for the derived ESCO/O*NET artifact, and comfort maintaining a build-time ingestion script against external public dumps?
6. **Fact-audit default:** is the provenance-map + lexical grounding verifier sufficient for the no-fabrication guarantee on resume tailoring / Q&A, or should the optional LLM fact-audit be **on-by-default whenever a key is present**?
7. **v1.5 default persona:** optimise the default home for the **active seeker** (Kanban/pipeline front-and-centre) or the **passive / new-grad** (gentle onboarding, coaching, fewer features)? They pull the default screen in opposite directions.

> **Review verdict:** *"Strong — ship the sequence with these targeted additions."* The plan is coherent and every claim it makes about the current code was verified true; the gaps above are the difference between a good plan and an excellent one.
