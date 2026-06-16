# Job Finder — Phased Roadmap

*Living design document — last updated 2026-06-10. Drafted via a multi-agent design pass and a completeness review; see the **Addendum** at the end for review corrections that supersede the body where they conflict.*


**Sequencing thesis.** One refactor gates the entire program: **extract the three in-memory dicts in `web.py` into a repository layer**, then land a **single typed config module** and a **thin service layer**. These are invisible to users but every durable feature (persistence, tracking, saved searches, alerts, analytics, feedback) is worthless without them. In parallel, **Now** ships the cheap, high-trust wins that need no new infrastructure: kill the plaintext-CV temp leak, harden the network boundary, add the explanation object, ship the guardrail verifier, and write the policy docs. **Persistence (encrypted SQLite) is the highest-value user-visible win** and the hinge between *Now* and *Next* — it converts "state survives restart" from aspiration to fact and unblocks the retention core. Heavy/optional intelligence (embeddings, LLM re-rank, learning loop) and the desktop installer come once their foundations exist.

---

## Now (v1.x) — Foundations, trust, and the seams everything depends on

| Item | Why | Effort | Dependencies |
|---|---|---|---|
| Extract `_PROFILES`/`_EXAMPLES`/`_DRAFTS` from `web.py` into a `store/`(repo) package behind `*Repo` Protocols with a `memory_repo.py` | The seam every later step depends on; pure refactor, zero behavior change, tests stay green | M | — |
| Single typed `config.py` (pydantic-settings, `SecretStr`) reading env → `~/.jobfinder/config.toml` → defaults; replace all scattered `os.environ.get` | One source of truth for keys/flags; prevents key leakage; gives non-coders an editable TOML; precondition for adding Adzuna/JSearch keys | S | — |
| Thin `services/` layer (cv/search/draft) + `Container` via `app.state`; slim routes to validate→call→map | Makes business logic testable without a server; removes fat handlers like `generate_drafts`; kills import-time global state | M | repo Protocols + config |
| Eliminate plaintext-CV temp file: parse uploads from in-memory `BytesIO`, not `tempfile(delete=False)` (`cv_parser.py:50`) | A crash mid-parse leaves a plaintext CV in the OS temp dir — a real privacy leak contradicting the local-first promise | S | — |
| Network-boundary hardening: `TrustedHostMiddleware` + same-origin CORS, Origin/Host validation, require `--allow-lan` + session token before non-loopback bind | Today `--host 0.0.0.0` exposes every CV and cover letter on the LAN with zero auth | M | — |
| Per-job **explanation object** (component scores + top 2–3 reasons) returned by `rank_jobs`, rendered in the match card | Builds trust; prerequisite for calibration, structured signals, and feedback; pure `matcher.py` refactor, no new deps | M | — |
| Score **calibration bands** (80+/60–79/40–59/<40) + labeled resume×JD fixture set + CI monotonicity assertions | Gives the 0–100 a defined, regression-protected meaning before more signals are added | M | explanation object |
| Parse the unused `Job.salary` + add seniority-gap scoring as bounded, explainable, never-penalizing multipliers; soft location/remote + recency nudge | Uses already-present-but-ignored fields so ranking reflects real fit, not just text overlap; stops good-but-imperfect-location matches being dropped | M | explanation object |
| **Guardrail verifier** (`guardrails.py`): block unresolved placeholders, lexically flag claimed hard-skills absent from the CV; run in `generate_draft` and on mark-ready; per-draft badges | Turns the anti-fabrication/no-placeholder promise from a prompt instruction into a verified offline property — highest-trust drafting change | M | — |
| Non-destructive draft regenerate: keep prior version as a restorable revision instead of DELETE-then-create | Current regenerate destroys the draft before generating — data-loss footgun if Claude returns worse copy | S | repo Protocols |
| App-shell left nav rail (Home·Search·Tracker·Outbox·Settings) + first-class **Settings** page (paste/store keys with live "key valid" check) | Env-var-only keys are a hard blocker for non-coders; the rail hosts every later surface | M | config |
| Dark/light/system theming + accessibility baseline (ARIA score donut, live-region search status, focus rings) + skippable 3-step onboarding ("use a sample CV") | Low-effort polish + WCAG 2.1 AA; empty app is currently unexplorable without a real CV | M | app shell |
| Source contract refactor: `Query`/`FetchContext`/`RawJob` split + central `normalize.py` (delete 3 duplicated `_strip_html`) + `@register`/`SourceMeta` registry; wrap `source.search` in `run_in_threadpool`; shared token-bucket limiter + global per-run cap | Unifies the repeated 5-arg `search()`; stops LinkedIn blocking the event loop; makes mass-scraping impossible by construction; one-line source registration | M | — |
| Add **Adzuna** source (free key, global, salary) as the README-recommended "turn this on" step | Highest-leverage coverage add: sanctioned API, worldwide, structured salary, real ToS — shifts gravity off the fragile LinkedIn scrape | S | source contract refactor |
| **Voice Profile** from examples → offline template generator (+ compact Claude instruction); `language` option + EN/DE/FR/ES/NL offline tables | Makes the default offline experience meaningfully better and bounds the few-shot block; cheap multi-language win for the EU-leaning sources | M | guardrail verifier |
| Policy docs + supply-chain hygiene: LICENSE, PRIVACY.md, ETHICS.md, SECURITY.md, CONTRIBUTING.md, CHANGELOG.md; pin deps with a lockfile + Dependabot; add Windows to CI matrix; gate on ruff/mypy/coverage≥85%/pip-audit; pin Actions to SHAs | Repo has no license/policy docs and Ubuntu-only CI though users run Windows; turns ethical boundaries from convention into contract | M | — |
| CI **security-regression suite**: no-secret-in-any-response, no-auto-submit-import (grep SMTP/Selenium/form-post), no-unexpected-outbound-host (allow-list = sources + `api.anthropic.com`) | Mechanically enforces the three core invariants so a future contributor can't accidentally break them | M | — |

## Next (v1.5) — Durable persistence and the retention core

| Item | Why | Effort | Dependencies |
|---|---|---|---|
| **Encrypted SQLite store** (`sqlite_repo.py`, WAL, owner-only ACL) at the app-data dir with forward-only migration runner; AES-GCM on `raw_text`/draft body/example text, key wrapped via OS keystore (DPAPI/Keychain/libsecret); make SQLite default | **The single highest-value user-visible win**: state survives restart, and a copied DB is useless on another machine. Central trust guarantee | L | repo Protocols + config |
| Promote **Application** above Draft (re-parent drafts 1:N, versioned); persist CVs (content-hash dedup), drafts, examples; "Save to pipeline" on match cards | Shifts the unit of retention from a transient draft to a durable application; directly kills the #1 limitation (state lost on restart silently invalidating `cv_id`) | M | encrypted store |
| **Lifecycle state machine** (saved→drafting→ready→applied→screening→interview→offer→rejected/withdrawn) with server-side transition validation replacing the draft\|ready whitelist; each change logs an immutable event | Turns binary status into a real pipeline; `applied_at` captured once anchors the funnel; terminal states stop nudges | M | Application entity |
| **Kanban Pipeline** board (renamed Outbox tab) with drag-to-transition, score/age/flag cards, filters, list-view toggle; per-application **detail drawer** (timeline, notes, contacts, versioned draft editor) | First visible retention payoff — a persistent campaign home; the durable timeline is what makes the tool trustworthy | L | lifecycle state machine |
| Layered **dedup keys** (URL key preferred, normalized company\|title\|location fallback) backing `job.id`, with per-source `job_sighting` (never drop, only link `also_seen_on`); promote Company to a deduped table | Replaces brittle `md5(...)` so the same posting across LinkedIn+Adzuna collapses to one durable row; lets apply default to the employer ATS front door | M | encrypted store |
| **Plugin registry for all three kinds**: entry-point discovery + `PluginManifest`; `/api/v1/plugins` shows only sources/matchers/generators whose key/deps are present; matchers (tfidf/semantic) and generators (template/claude) become discovered peers | UI stops offering things that fail at runtime; third-party sources/Ollama generator install without core edits | M | services layer |
| Add **ATS sources** (Greenhouse/Lever/Ashby via user-editable `ats_companies.yml`) + generic `RssSource` + Jooble/The Muse + `requests-cache` SQLite HTTP layer (per-source TTLs) + provenance-preserving cross-source dedup + `healthcheck()` source-status picker + tos_tier consent gate | ATS is the most ethical full-description source class and the app's differentiator; caching removes most 429 pressure; consent + status make coverage and the ethics boundary visible | L | source contract refactor + plugin registry |
| Bundled **skills graph**: `build_skill_graph.py` ingests public ESCO (CC-BY) + O*NET into `skills_graph.json`; `taxonomy.py` loader; make `skill_overlap` taxonomy-aware (exact 1.0 / broader 0.7 / sibling 0.4) with relation tooltips | The highest-leverage matching change; fixes false "missing skill" chips, reduces pedigree bias, unblocks the upskilling report | L | explanation object |
| `POST /api/feedback` (thumbs, hide company/role) + log implicit signals (drafted+, ready/exported++, dismissed−) to the encrypted store | No feedback signal exists today; capturing it (much free from existing draft tracking) is the foundation of any learning loop | M | encrypted store |
| Offline **upskilling report**: per-job fit-gap grouped by taxonomy cluster + cross-cluster "what to learn next" ranked by frequency × score-lift | Turns missing-skills data into a first-class offline product surface and a reason to return | M | taxonomy-aware overlap |
| **Resume tailoring** (`tailor.py`): section/bullet segmentation, reorder skills, rank bullets by TF-IDF overlap, emit tailored resume with a **provenance map**; **Answer Profile** + screening-Q&A drafter (factual answers from profile only) | The biggest missing artifact, higher-leverage than letters; provenance is what makes it safe; screening Q&A covers common ATS fields honestly | L | guardrail verifier |
| Versioned **`/api/v1`** with `{data,warnings,meta}` envelope + central exception→HTTP mapper; one-click **Export-all** (JSON/ZIP) and **crypto-shred Delete-all**; point-of-action disclosure banners; recorded-fixture source tests + mocked Claude-path test; structured redacted logging + `/api/health` | Stable contract; GDPR-shaped data rights now that CVs persist to disk; trust built where data flows; LinkedIn drift becomes a caught failure not a silent bug | M–L | encrypted store; services layer |

## Later (v2.0) — Alerts, deeper intelligence, and the installer

| Item | Why | Effort | Dependencies |
|---|---|---|---|
| **Saved searches + alerts**: persist `SearchSettings`+cv_id+cadence, re-run via opt-in in-process scheduler thread (FastAPI lifespan, ≥6h rate-limit, source back-off), diff last-seen ids → offline in-app "New matches" inbox; `Notifier` protocol with opt-in desktop toast + user-SMTP digest + `run_alerts` CLI | The actual return-visit driver; fully offline by default, no Redis/Celery; rate-limiting respects source fragility | L | encrypted store + plugin registry + reminder engine |
| Local **reminder engine** + rule-based nudges (auto +7d on applied, 3-day ready nudge, post-interview prompt) via asyncio scheduler + startup catch-up; in-app notification bell + "Needs your attention" list | Core retention mechanic; offline, rule-based, auto-cancels when status advances so it never nags | M | lifecycle state machine |
| **Insights** tab: funnel (saved→applied→interview→offer), apps/week, response/interview rates, time-to-response, response-by-source/score-band, rejection tags — inline SVG/CSS, no charting lib | The motivational payoff of a multi-week campaign; needs accumulated data | M | lifecycle state machine |
| **Local logistic re-weighter** (`feedback.py`, bounded ±15pt, Bayesian per-cluster affinity priors, incremental retrain, one-click reset, "personalized" badge) + per-user calibration (isotonic/Platt) | Lets the ranker improve with use while staying explainable, cold-start-safe, bubble-resistant, and fully on-device | L | feedback logging + taxonomy |
| Optional **Stage B/C precision**: MiniLM bi-encoder over top-50 + cross-encoder over top-20 (behind semantic toggle); opt-in **Claude top-15 re-rank** (bounded nudge + one-line rationale, cached by cv-hash×job-id) | Sharper ordering where it matters; heavy models and LLM stay strictly optional, lexical core authoritative | M each | explanation object; drafts.py anthropic plumbing |
| **PyInstaller + pywebview signed desktop app** (`JobFinder-Setup.exe`/`.dmg`/`.AppImage`) via GitHub Actions release matrix; `__version__` single-source into `/api/health` + footer; SemVer + tagged releases; auto-update check | The headline non-coder deliverable: double-click install, no Python/terminal; makes time-to-first-match <3 min real | L | `pyproject.toml` console-script |
| **Application Pack** export + per-field copy UI (letter+resume+answers+contacts); ethical one-click apply-handoff; Claude resume-phrasing rewrite (facts locked); optional LLM fact-audit pass | The ToS-safe autofill story — everything to apply by hand fast, nothing automated; upgrades tailored resumes while keeping facts locked | M | resume tailoring + screening Q&A |
| Interview-stage support (date capture, `.ics` export, prep notes, thank-you reminders); responsive/mobile + opt-in LAN toggle (bind 0.0.0.0 with QR); Docker/compose with mounted `./data` volume; privacy wipe/export in Settings; bulk pipeline actions + CSV | Deepens late-funnel value; true mobile without exposing a port; self-host home; portability | M (each) | pipeline + persistence + desktop app |
| Playwright E2E happy-path + Hypothesis parser fuzz + CI perf-smoke (>2× regression fails); shared source-politeness layer with per-source rate-policy assertion; passphrase-gated decryption + nightly source-drift canary | Locks the full workflow and perf budgets; ethical defaults by construction; defense-in-depth | M (each) | `/api/health`; encrypted store |

## Vision (north-star bets)

| Item | Why | Effort | Dependencies |
|---|---|---|---|
| Background **"career watch"** daemon (opt-in, always-on local, scheduled saved searches → next-open digest) | The fully-realized passive-persona "quiet co-pilot" with zero cloud — the ultimate privacy differentiator vs LinkedIn | XL | saved searches + scheduler |
| **Smart next-action coach** ("today's 3 moves") + outcome-driven feedback loop ("roles like the ones you got interviews for"); interview-prep + offer-comparison (Land stage) | Turns the tracker from passive memory into an active daily-habit assistant; completes the journey to *land* | XL | advanced analytics; feedback loop |
| Plugin author **SDK + cookiecutter** + `jobfinder.plugins` entry-point spec; adopt schema.org JobPosting/JSON-feed ingestion | Coverage scales beyond the core team while trust-tier/rate-cap/no-submit guardrails stay centrally enforced; the cleanest long-term path away from scraping | L–XL | plugin registry (all kinds) |
| Optional **self-hosted encrypted device-sync** (user owns the endpoint; `postgres_repo` behind the same Protocol) | Addresses the single-device limitation without compromising local-first; the repository seam powers a future hosted variant without touching services/UI | XL | stable migration runner + repository layer |
| **Trustworthy-local-first standard**: reproducible/signed builds, third-party security audit + published report, SLSA provenance, CI-verified "never phones home" guarantee on every release | North star — a reference example of a privacy-respecting local AI tool a non-technical user trusts with their CV like a local password manager | XL | all prior security/quality items |

---

## KPIs

**Trust & privacy (the differentiating KPIs):** 100% of releases pass the no-unexpected-outbound-host CI test; **0** plaintext CVs on disk outside the encrypted store; Delete-all crypto-shred verifiable in **<2s**; 100% of off-device data flows have an at-point-of-action disclosure.

**Quality:** coverage **≥85%**; main green ≥99% of trailing 30 days; PR CI **<3 min**; source-drift MTTD **<48h** (canary catches breakage before users); **0** known high/critical dependency CVEs at release; **0** drafts that pass the grounding check while claiming a credential absent from the CV.

**Product value (local/opt-in only — never silent telemetry):** time-to-first-match **<3 min** from launch (via the prebuilt installer); ≥70% of top-10 results rated relevant in opt-in thumbs feedback (precision@10, stored locally); ≥60% of generated drafts edited-and-exported rather than discarded; saved-search return rate and pipeline conversion shown in the private Insights view.

## Sequencing Rationale

1. **The repo extraction + config + service layer come first** because they are the seams every durable feature hangs on, and they ship green with zero behavior change — de-risking the program before any user-facing bet.
2. **Trust wins land in Now, not later**, because they are cheap, mechanically enforceable, and the moment persistence arrives "it disappears on restart" stops being the privacy story — so the encrypted store and the CI invariant tests must precede, not follow, durable storage.
3. **Persistence is the hinge.** It is invisible but gates the entire retention core (tracking, saved searches, alerts, analytics, feedback) and is the highest-value user-visible win — so it opens *Next* and everything campaign-shaped depends on it.
4. **The plugin registry precedes broad source/matcher expansion** so adding Adzuna/ATS/Ollama is a registration, not a core edit, and the no-submit guardrails are enforced by the protocol rather than by reviewer vigilance.
5. **The skills graph precedes the learning loop and upskilling report** because trustworthy partial-credit matching is the substrate both build on.
6. **Heavy/optional intelligence and the installer are Later**, gated on their foundations (explanation object, feedback logging, `pyproject.toml`), keeping the offline-first default authoritative throughout.
7. **Alerts deliberately avoid Redis/Celery** — an opt-in in-process scheduler then an OS-scheduled CLI — honoring "runnable by a non-technical person" absolutely, with the same service/repo code reused at every tier.

---

## Addendum — Sequencing Corrections (from design review)

These adjustments are **authoritative** over the phase tables above. Most are cheap, dependency-light fixes that the review found mis-placed or missing — pull them into **Now**.

### Add to / pull into Now (v1.x)

| Item | Why | Effort | Dependencies |
|---|---|---|---|
| **Flip the default source** `['linkedin']` → `['remotive','arbeitnow']` in `engine.py` `SearchSettings` | One-line change that resolves a live ethics-principle contradiction — today's default opts the user into the grayest source with no disclaimer. Must not wait for the source-contract refactor | S | — |
| **"Confirm your parsed profile" onboarding step** (show extracted skills/title/location/name; let the user fix them) | The whole funnel's accuracy rests on `cv_parser` heuristics; cheap, needs no persistence, and immediately lifts match quality + trust. Pull ahead of the v1.5 skills graph | S | app shell |
| **Model-tier + per-run cost preview** on the Settings page (Haiku / Sonnet / Opus selector; estimated tokens/cost before a batch) | Resume tailoring + screening-Q&A + fact-audit + re-rank all multiply per-run Opus spend on the user's own key; tier selection is cheap and must land **before** those Later items multiply cost | S | Settings page |

### Pair with the encrypted store in Next (v1.5)

| Item | Why | Effort | Dependencies |
|---|---|---|---|
| **Key-export / recovery mode** (passphrase-derived key or printable recovery code at setup; "recover from passphrase" flow) — ship in the **same unit of work** as the encrypted SQLite store | OS-keystore-wrapped keys die on reinstall/account change → silent total data loss. Shipping encryption without a recovery path guarantees a future data-loss class the moment the first user reinstalls Windows | M | encrypted store |
| **LLM-egress disclosure + optional PII-redaction toggle** before sending CV+JD to Anthropic; first-use per-send confirmation | The one real egress carries the *whole* CV; a local-first product must disclose what leaves and offer to minimize it | S | drafts.py / Settings |

### Make these prerequisites / gates (not afterthoughts)

| Item | Why |
|---|---|
| **NOTICE / third-party-licenses aggregation** is a prerequisite *on* the PyInstaller release task | Distributing a signed binary bundling ESCO/O*NET/MiniLM + transitive deps without a NOTICE file is a redistribution-compliance blocker, not a nice-to-have |
| **Gate the ML ranking stack** (MiniLM → cross-encoder → learned re-weighter → calibration) on a **measured win against the calibration fixtures** | Treat Stage B/C/D as *experiments kept only if they beat the fixture set*, not scheduled work — preserves the "runs on any laptop, no download" promise |
| **Single-writer discipline** for the opt-in scheduler | WAL + `busy_timeout` + a write lock/queue so background alert/reminder sweeps don't contend with foreground UI writes on the one SQLite file |

### KPI corrections

- **Scope "0 plaintext CVs on disk"** to *at-rest application storage*, excluding user-initiated exports (the JSON export is plaintext by design).
- **Reframe field KPIs as design budgets.** Telemetry-free means *time-to-first-match <3 min* and *precision@10* can't be measured in production — validate them in CI / manual QA, not as field metrics.
- **Add a reliability budget:** *search-success / non-empty-result rate* and a graceful-degradation path for zero-results / 429 / source-HTML-drift / scanned-PDF (`looks_empty`) cases.
