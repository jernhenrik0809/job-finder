# Job & consulting sources for Denmark

The definitive catalog of every researched job, freelance and consulting source relevant to a
Denmark-based search — **including ones not (yet) integrated**, so this doubles as a manual
where-to-look list. The app's actually-wired sources live in
[`jobfinder/sources/`](../jobfinder/sources/); this document is the map around them.

**Status legend**

- **Integrated** — wired as a live source in the app (a class in `jobfinder/sources/`).
- **Integrable** — free + public API/RSS (no key, or a free self-signup key) + Denmark-relevant +
  ToS-friendly; buildable into a source with the existing patterns. Marked *(now)* if ready to
  build today, or *(optional key)* if it needs a free self-signup credential.
- **Document-only** — exists and is DK-relevant, but cannot be cleanly/ethically ingested
  (login / partner / paid, wrong shape, or scrape-fragile). Listed for completeness and as places
  to keep a profile or apply manually.

**Access types** — *no-key API/RSS* = public, anonymous · *free-key* = free self-signup credential
(env var / ⚙ Settings) · *partner/paid* = manual onboarding or CPC contract · *scrape* = HTML-only,
no machine feed · *login* = gated behind an account.

> **Ground rules this catalog respects:** Denmark-relevant only; nothing that requires login
> impersonation or violates a board's ToS is integrated; keyed sources resolve their credential
> from the secrets overlay and are skipped (not failed) when unset; and a keyed source's errors
> never echo its key. See [`docs/SECURITY.md`](SECURITY.md) and [`docs/ETHICS.md`](ETHICS.md).

---

## Integrated (13 live sources)

These are wired and tested. The **default** no-key set runs unless you pick others; **opt-in**
sources are unticked by default; **keyed** sources light up once their free credential is set in
⚙ Settings.

| Name | What | DK relevance | Access | Default? | Module |
|---|---|---|---|---|---|
| Remotive | Free remote-jobs JSON API | Some (remote, DK-eligible) | no-key API | ✅ default | `remotive.py` |
| Arbeitnow | Free European job-board JSON API | Some (EU-heavy) | no-key API | ✅ default | `arbeitnow.py` |
| The Hub (`thehub.io`) | Nordic startup/scale-up jobs (`countryCode=DK`) | Strong | no-key API | ✅ default | `thehub.py` |
| The Muse | Curated company/job listings, filtered to DK cities | Some | no-key API | ✅ default | `themuse.py` |
| **it-jobbank.dk** | Denmark's leading IT/tech board (StepStone family) | Strong | no-key RSS | ✅ default | `itjobbank.py` |
| **HR-Manager / SRL** | DK public-sector ATS — state (Statens Rekrutteringsløsning) + Region Syddanmark | Strong | no-key JSON | ✅ default | `hrmanager.py` |
| Jobindex (RSS) | Denmark's **largest** job board (absorbed Ofir) | Strong | no-key RSS | opt-in | `jobindex.py` |
| **Jobicy** | Free remote-jobs board, `geo=denmark` scope | Some | no-key API | opt-in | `jobicy.py` |
| LinkedIn (guest) | Public `jobs-guest` search endpoint (cards + per-job description) | Strong (geoId-filterable) | no-key (unofficial) | opt-in | `linkedin.py` |
| Adzuna (dk) | Aggregator with a dedicated Denmark endpoint + structured salary | Strong (`/jobs/dk/`) | free-key | keyed | `adzuna.py` |
| Jooble (dk) | Job-search API covering Denmark | Strong | free-key | keyed | `jooble.py` |
| **Careerjet** | Large aggregator with a Danish portal (`da_DK`, `careerjet.dk`) | Strong | free affiliate id | keyed | `careerjet.py` |
| JSearch (RapidAPI) | Aggregates Google for Jobs (LinkedIn/Indeed/Glassdoor) | Strong (query-scoped) | free-key | keyed | `jsearch.py` |

**Notes on the integrated set**

- **HR-Manager / SRL is the highest-value DK public-sector integration.** One generic source
  (`hrmanager.py`) queries a curated list of HR-Manager *customer* aliases and merges them. The
  `statensrekrutteringsloesning_tr` alias (Statens Rekrutteringsløsning) aggregates vacancies
  across ~140 Danish **state** institutions — a ToS-clean, programmatic stand-in for the
  login-gated Jobnet/STAR — and `regionsyddanmark` adds regional health/hospital jobs. More
  regions/kommuner/universities drop in by adding their `customer=` alias (the alias is a public
  identifier, not a secret). It returns no-auth JSON and survives a single failing alias.
- **it-jobbank / Jobindex** share the StepStone-family RSS shape (ISO-8859-1, `"Role, Company"`
  titles) and reuse the same parsing approach. it-jobbank's RSS omits the location span Jobindex
  carries, so its `location` field can come up empty (title/company/url/date are reliable).
- **Careerjet** is the strongest keyed *general-jobs* add for DK; its request URL carries the
  affiliate id, so its error text is sanitised to the exception type name only.
- **LinkedIn** is polite/low-volume only, backs off on HTTP 429, and is never a default.

---

## Freelance & consulting (gigs)

The Danish consulting/freelance space is overwhelmingly login-, approval- or paid-gated — almost
nothing exposes an open gig feed. Two have buildable read APIs behind a free credential; the rest
are document-only (keep a profile, apply/await invites).

| Name | What | DK relevance | Access | Status | Notes |
|---|---|---|---|---|---|
| **Brainville** | Nordic marketplace for freelancers/consultants + brokers (ex-Resrc); 100s of IT/business gigs/week | Strong | free-key (`BRAINVILLE_USER_KEY`+`BRAINVILLE_SENDER_KEY`; one-click dev access) | **Integrable (optional key)** | Documented `POST /v2/market/search` REST API v2 — the best-verified DK consulting source. Captures Right People Group gigs transitively. The top candidate for the next keyed source. |
| **Freelancer.com** | Global project marketplace; documented REST API + Python SDK | Global/remote (weak DK) | free static OAuth token (`FREELANCER_TOKEN`) | **Integrable (optional key)** | `GET /api/projects/0.1/projects/active/` with a `Freelancer-OAuth-V1` header. Single static token, plain GET. Off by default if added. |
| emagine (ex-ProData Consult) | Large independent IT/business consulting broker, HQ Copenhagen; public DK-filterable freelance board | Strong | scrape (JS-rendered) | Document-only | `portal.emagine.org/jobs/` is genuinely public + Denmark-filterable but JS-rendered; needs the undocumented internal XHR JSON. Revisit if that endpoint is identified. |
| Onsiter | Nordic contractor/consultant aggregator (~1000 assignments/day, DK confirmed) | Strong | scrape (index 403s bots) | Document-only | Detail pages public; index page Cloudflare-protected. No feed/sitemap confirmed. |
| Ework Group / Verama | Top Nordic independent-consultant broker; 700+ assignments/mo on Verama | Strong | login (SPA) | Document-only | `app.verama.com` SPA needs a free login; no public REST/RSS confirmed. |
| 7N | Danish-origin elite IT consultancy/broker; agent-mediated | Strong | scrape (JS ATS) | Document-only | `jobs.7n.com/job-offers` is a JS-rendered ATS shell; value is agent representation, not an open feed. |
| Right People Group | Copenhagen IT/management consulting broker; register-and-get-contacted | Strong | login / email alerts | Document-only | No public board/API. **Its gigs flow into Brainville** — integrate Brainville to capture them. |
| Worksome | Danish-origin Freelance Management System; vetted tech freelancers | Strong (the most DK-relevant freelance platform) | login + GraphQL (auth-only) | Document-only | Private client talent pools; no public listings. Its GraphQL API manages your own contracts/payments, not open gigs. Create a profile to enter pools. |
| Malt (incl. merged Comatch) | Largest European freelance/consulting marketplace; Nordics region covers DK | Some | profiles only (no public jobs API) | Document-only | Reverse marketplace — clients invite freelancers; only freelancer profiles are public. Be present, don't query. |
| Giig (`giig.dk`) | Danish freelancer platform (marketing/design/dev/IT) | Strong | login (profile/lead model) | Document-only | Companies browse profiles and push tasks to your inbox; no open-gig feed. |
| Upwork | Largest global freelance marketplace; GraphQL API | Global (weak explicit DK) | free-key but OAuth2 3-legged | Document-only | `marketplaceJobPostingsSearch` is readable, but a heavy 3-legged token flow + ToS limits on automated use. |
| Toptal | Closed vetted talent network (top ~3%) | Global | no public board/API | Document-only | Staff-matched; nothing to ingest. Apply to join. |
| Freelancermap | Pan-EU IT freelance projects; public Denmark list page | Some (DACH-centric) | scrape (HTML, no read API) | Document-only | Enterprise XML/JSON is import-only; no current DK RSS verified. |
| Fiverr | Productized-gig marketplace | Global | no API (anti-bot) | Document-only | Wrong shape (gig supply, not job demand). |
| Contra | Commission-free freelance platform (US-centric) | Minimal | login | Document-only | Opportunities behind login; its "API" is a product embed, not a jobs feed. |
| Twago | Berlin-founded EU freelance project marketplace | Some | login | Document-only | Login-gated, small footprint; no clean feed. |
| Outvise | European freelance/expert network (telecom/tech/data) | Minimal | login (curated) | Document-only | No readable listings feed; register a profile. |
| Useme | Polish-origin freelance board | Minimal | employer-only API; scrape for reads | Document-only | Public API is employer/deal-oriented (no list-jobs read); negligible DK. |
| Expert360 / Catalant | APAC / US enterprise consulting marketplaces | Minimal | no public feed | Document-only | No DK relevance; private engagements. |

---

## Job boards (employee roles)

| Name | What | DK relevance | Access | Status | Notes |
|---|---|---|---|---|---|
| it-jobbank.dk | Denmark's leading IT/tech board (StepStone Group) | Strong | no-key RSS | **Integrated** | `itjobbank.py` — see the integrated table above. |
| Jobindex.dk | Denmark's largest job board (absorbed Ofir) | Strong | no-key RSS | **Integrated** | `jobindex.py` — see above. |
| **StepStone.dk** | Major Danish general/professional board (StepStone Group) | Strong | no-key RSS | **Integrable (now)** | `?format=rss` on `/job/{location}` and `/jobsoegning` (e.g. `/job/danmark?format=rss`). Same RSS shape as Jobindex/it-jobbank — drops straight into that parser. (`api.stepstone.com` is employer-side posting — ignore it.) High-value next no-key add. |
| Jobfinder.dk / TechJob.dk | DK's largest engineer/IT/tech board (Teknologiens Mediehus / Ingeniøren) | Strong | scrape (jobs feed empty) | Document-only | `jobfinder.dk` 301→`techjob.dk`; `rss.xml` is an empty articles feed; jobs view has no RSS/JSON. Drupal HTML scrape only. |
| Jobsora (`dk.jobsora.com`) | Job aggregator with a Danish site | Strong | partner (inbound XML only) | Document-only | Only an inbound "post-to-us" partner XML; no outbound search/pull API. |
| Talent.com (dk) | Global aggregator (78+ countries incl. DK) | Strong | partner/paid (CPC) | Document-only | Publisher XML/API gated behind a manual CPC partnership; no free instant key. |
| WhatJobs | Global aggregator with DK presence; FeedAPI | Some | partner (token by request) | Document-only | FeedAPI needs an `x-feed-token` issued only after contacting them. |

---

## Aggregators & remote

| Name | What | DK relevance | Access | Status | Notes |
|---|---|---|---|---|---|
| Jobicy | Free remote-jobs board with a public JSON API | Some (explicit `geo=denmark`) | no-key API | **Integrated** | `jobicy.py` — see the integrated table above. |
| Careerjet | Large job-aggregator search engine with a Danish portal | Strong (`da_DK`) | free affiliate id | **Integrated** | `careerjet.py` — see above. |
| Adzuna | Aggregator with a dedicated Denmark endpoint | Strong (`/jobs/dk/`) | free-key | **Integrated** | `adzuna.py`. |
| Jooble | Job-search API covering Denmark | Strong | free-key | **Integrated** | `jooble.py`. |
| JSearch (RapidAPI) | Aggregates Google for Jobs | Strong | free-key | **Integrated** | `jsearch.py`. |
| **Findwork.dev** | Tech-jobs search engine with a clean REST API | Minimal (incidental DK) | free token (`FINDWORK_TOKEN`) | **Integrable (optional key)** | `GET /api/jobs/` with `Authorization: Token <key>` (not Bearer). Tech-only, low DK yield — an optional complement. |
| EURES | EU cross-border public jobs portal incl. DK | Some | none (ToS forbids scraping) | Document-only | **Ruled out**: undocumented backend, ToS forbids automated extraction. DK state coverage is better via HR-Manager/SRL + Jobindex. |

---

## Academic & public sector

| Name | What | DK relevance | Access | Status | Notes |
|---|---|---|---|---|---|
| HR-Manager / Talentech JobPortal | The recruitment ATS behind a huge share of DK public-sector, university & regional employers | Strong | no-key REST/RSS | **Integrated** | `hrmanager.py` — generic, parameterised by a list of `customer=` aliases. See the integrated table. |
| Statens Rekrutteringsløsning (SRL) | Centralized Danish **state** recruitment (~140 institutions migrating by end-2026) | Strong | no-key (HR-Manager alias `statensrekrutteringsloesning_tr`) | **Integrated** | Shipped as a preset alias of `hrmanager.py`. One call = cross-ministry state coverage. |
| Region Syddanmark | Regional (hospital/health) vacancies | Strong | no-key (HR-Manager alias `regionsyddanmark`) | **Integrated** | Shipped as a preset alias of `hrmanager.py`. Add more regions/kommuner by discovering their aliases. |
| University of Copenhagen (KU) | `employment.ku.dk` vacancies (academic + admin) | Strong | no-key (HR-Manager alias TBD) | **Integrable (now, alias pending)** | HR-Manager-backed; confirm the KU `customer=` alias once, then it drops into `hrmanager.py`'s alias list. |
| EURAXESS Jobs (Denmark facet) | Pan-European research-jobs portal (postdoc/PhD/fellowships); KU/DTU/AU post here | Strong | scrape (no read API/RSS) | Document-only | Only API is inbound XML submission. The DK-facet search is server-rendered HTML (scrapeable, no JS) but fragile + ToS asks for politeness. High-quality DK research jobs; revisit as an optional scrape. |
| DTU (Technical University) | DTU vacancies on Oracle Recruiting Cloud (not HR-Manager) | Strong | no-auth CE endpoint (host/site-specific) | Document-only | The Oracle `recruitingCEJobRequisitions` CE endpoint works unauthenticated, but host + `siteNumber` are DTU-specific and Oracle changes CE params — fragile. Each DK uni on Oracle needs its own host+site. |
| Akademikernes Jobbank (`jobbank.dk`) | DK's largest academic/graduate career board | Strong | RSS unconfirmed / scrape | Document-only | An RSS link is reportedly advertised but the literal feed URL couldn't be confirmed; the board exposes no verified RSS/XML/API (email jobagent only). Promote to integrable once a working feed URL is verified. |
| Graduateland (now JobTeaser) | Copenhagen-founded student/graduate portal; runs ~30 university portals | Strong | login (SPA; 410 on listings) | Document-only | `graduateland.com/s/jobs/*` 301→`jobteaser.com` → login-walled SPA; no public feed. Partly mitigated: many roles also land on The Hub (integrated) and on HR-Manager feeds. |
| Emply | Legacy DK public/uni/kommune ATS | Strong (shrinking) | per-tenant (fragmented) | Document-only | Being decommissioned — institutions migrating to SRL (on HR-Manager) by end-2026. Invest in the SRL feed instead. |
| Lederne.dk jobbank | A-kasse/org for managers | Some | internal + member-only | Document-only | "Ledige stillinger" = Lederne's own staff openings; member tool is login-gated. No public external-job feed. |
| CA a-kasse | A-kasse/career org for business academics | Some | none found | Document-only | No public jobbank/feed; offering is career advising. |
| aka.dk JobMatch | Akademikernes A-kasse member CV-matching | Strong | login (member-only) | Document-only | Login-gated CV-matching, not a browsable board. |

---

## Niche / staffing

| Name | What | DK relevance | Access | Status | Notes |
|---|---|---|---|---|---|
| Academic Work (`academicwork.dk`) | Nordic staffing for young professionals/students | Strong | scrape (no feed) | Document-only | `/jobs` is server-rendered HTML; `?format=rss` returns HTML, no API. Email jobagent only. |
| Moment.dk | DK's largest temp/vikar + recruitment agency (150+ roles) | Strong | scrape (JS-heavy) | Document-only | No RSS/API; `data.moment.dk` backend undocumented; listings JS-rendered. |
| Adecco / Randstad Denmark | Large international staffing agencies in DK (temp + permanent) | Strong | scrape (custom JS apps) | Document-only | No public API/RSS; only unofficial scrapers exist. |

---

## Investigated and excluded (not DK freelance/consulting platforms)

| Name | Finding |
|---|---|
| Bloffin | No such DK freelance platform; only unrelated "Bloffin Technologies" (cloud services). Skip. |
| Inhouse | Not a distinct platform; maps to in-house corporate consultancies or Randstad Inhouse staffing. Skip. |
| Ballou | Ballou PR — a tech PR agency, not a marketplace and not DK-based. Skip. |
| Comatch | Acquired by and fully merged into Malt (2022); covered by the Malt entry. |

---

## What to integrate next (priority order)

1. **StepStone.dk** — no-key RSS, same parser as Jobindex/it-jobbank. Pure win; no credential.
2. **Brainville** — the best-verified DK *consulting/gig* source; free one-click dev key, documented
   REST API. Would also transitively capture Right People Group gigs.
3. **University of Copenhagen (KU)** — confirm the one HR-Manager `customer=` alias, then it's a
   one-line addition to `hrmanager.py`.
4. **Findwork.dev** / **Freelancer.com** — optional keyed complements (low DK yield / weak DK,
   respectively); add behind a free token, off by default.

Everything else above is document-only by nature (login / partner / paid / scrape-fragile) — kept
here as the manual where-to-look list, not integration targets.
