# Job & consulting sources for Denmark (and remote / short-term)

The definitive catalog of every researched job, freelance and consulting source relevant to a
Denmark-based search — **including ones not (yet) integrated**, so this doubles as a manual
where-to-look list. The app's actually-wired sources live in
[`jobfinder/sources/`](../jobfinder/sources/); this document is the map around them.

Scope: **Denmark-relevant** roles first, broadened to **remote / short-term (freelance, contract,
gig)** sources that a Denmark-based person can take. Local job boards stay Denmark-scoped; the
remote and gig sources are global by nature.

**Status legend**

- **Integrated** — wired as a live source in the app (a class in `jobfinder/sources/`).
- **Integrable** — free + public API/RSS (no key, or a free self-signup key) + relevant +
  ToS-friendly; buildable with the existing patterns. Marked *(now)* if ready today or
  *(optional key)* if it needs a free self-signup credential.
- **Document-only** — exists and is relevant, but cannot be cleanly/ethically ingested
  (login / partner / paid, ToS forbids automated use, wrong shape, or scrape-fragile). Listed for
  completeness and as places to keep a profile or apply manually.

**Access types** — *no-key API/RSS* = public, anonymous · *free-key* = free self-signup credential
(env var / ⚙ Settings) · *partner/paid* = manual onboarding or CPC contract · *scrape* = HTML-only,
no machine feed · *login* = gated behind an account.

> **Ground rules this catalog respects:** relevant sources only; nothing requiring login
> impersonation or violating a board's ToS is integrated (this is why Himalayas and EURES are
> document-only despite working technically); keyed sources resolve their credential from the
> secrets overlay and are skipped (not failed) when unset; and a keyed source's errors never echo
> its key. See [`docs/SECURITY.md`](SECURITY.md) and [`docs/ETHICS.md`](ETHICS.md).

---

## Integrated (21 live sources)

Wired and tested. The **default** no-key set runs unless you pick others; **opt-in** sources are
unticked by default; **keyed** sources light up once their free credential is set in ⚙ Settings.

### Denmark

| Name | What | DK relevance | Access | Default? | Module |
|---|---|---|---|---|---|
| The Hub (`thehub.io`) | Nordic startup/scale-up jobs (`countryCode=DK`) | Strong | no-key API | ✅ default | `thehub.py` |
| The Muse | Curated company/job listings, filtered to DK cities | Some | no-key API | ✅ default | `themuse.py` |
| **it-jobbank.dk** | Denmark's leading IT/tech board (StepStone family) | Strong | no-key RSS | ✅ default | `itjobbank.py` |
| **HR-Manager / SRL** | DK public-sector ATS — state (Statens Rekrutteringsløsning) + Region Syddanmark | Strong | no-key JSON | ✅ default | `hrmanager.py` |
| **StepStone.dk** | Major Danish general/professional board (StepStone family) | Strong | no-key RSS | opt-in | `stepstonedk.py` |
| Jobindex (RSS) | Denmark's **largest** job board (absorbed Ofir) | Strong | no-key RSS | opt-in | `jobindex.py` |
| Adzuna (dk) | Aggregator with a dedicated Denmark endpoint + structured salary | Strong (`/jobs/dk/`) | free-key | keyed | `adzuna.py` |
| Jooble (dk) | Job-search API covering Denmark | Strong | free-key | keyed | `jooble.py` |
| Careerjet | Aggregator with a Danish portal (`da_DK`, `careerjet.dk`) | Strong | free affiliate id | keyed | `careerjet.py` |

### Remote / global

| Name | What | Relevance | Access | Default? | Module |
|---|---|---|---|---|---|
| Remotive | Free remote-jobs JSON API | Remote, DK-eligible | no-key API | ✅ default | `remotive.py` |
| Arbeitnow | Free European job-board JSON API | EU incl. DK | no-key API | ✅ default | `arbeitnow.py` |
| Jobicy | Free remote-jobs board, `geo=denmark` scope | Remote, DK-scoped | no-key API | opt-in | `jobicy.py` |
| **RemoteOK** | Large global remote-jobs JSON API | Remote, global | no-key API | opt-in | `remoteok.py` |
| **We Work Remotely** | Major remote-jobs board, RSS | Remote, global | no-key RSS | opt-in | `weworkremotely.py` |
| **Working Nomads** | Curated remote-jobs JSON feed | Remote, global | no-key API | opt-in | `workingnomads.py` |
| JSearch (RapidAPI) | Aggregates Google for Jobs (LinkedIn/Indeed/Glassdoor) | Query-scoped | free-key | keyed | `jsearch.py` |
| LinkedIn (guest) | Public `jobs-guest` search endpoint (cards + per-job description) | Strong (geoId-filterable) | no-key (unofficial) | opt-in | `linkedin.py` |

### Company boards (ATS)

| Name | What | Relevance | Access | Default? | Module |
|---|---|---|---|---|---|
| **Greenhouse / Lever / Ashby** | The public, no-key board APIs behind companies' own careers pages — **full descriptions** from a curated list of Danish/Nordic firms (Trustpilot, Too Good To Go, Veo, Corti, Pleo, Lunar) | Strong (named DK firms) | no-key | opt-in | `ats.py` |

### Freelance / short-term gigs

| Name | What | Relevance | Access | Default? | Module |
|---|---|---|---|---|---|
| **Verama** (Ework Group) | Public feed of open **consulting assignments** — fixed-term contracts with rate, hours/week, start/end dates | Strong (Nordic incl. DK) | no-key | opt-in | `verama.py` |
| **Hacker News** | Monthly "Freelancer? Seeking freelancer?" threads via the public Algolia API | Remote/tech gigs | no-key | opt-in | `hackernews.py` |
| **Freelancer.com** | Active short-term project listings (gigs) via the official Projects REST API | Global, remote gigs | free token | keyed | `freelancer.py` |

> **"Consulting / contract only" filter:** a search toggle (`gigs_only`) keeps just contract/freelance
> work across every source that exposes an employment type — `Job.employment_type` is populated from
> Remotive's `job_type`, We Work Remotely's `<type>`, Jobicy's `jobType[]`, and the pure-gig sources
> (Verama/Hacker News/Freelancer are always contract/freelance). This turns the app into a job board
> for a consultant without needing consulting-only sources.

**Notes on the integrated set**

- **HR-Manager / SRL is the highest-value DK public-sector integration.** `hrmanager.py` queries a
  curated list of HR-Manager *customer* aliases and merges them. `statensrekrutteringsloesning_tr`
  (Statens Rekrutteringsløsning) aggregates ~140 Danish **state** institutions — a ToS-clean
  programmatic stand-in for the login-gated Jobnet/STAR — and `regionsyddanmark` adds regional
  health jobs. (University of Copenhagen sits under this same customer, but the syndicated feed
  currently excludes KU vacancies — see below.)
- **StepStone.dk / it-jobbank / Jobindex** are the same StepStone/Jobindex RSS family (ISO-8859-1,
  `"Role, Company"` titles). StepStone.dk's location/company live in the description HTML
  (`span.job-location` / `div.job-company`), unlike Jobindex's `.jix_robotjob--area`.
- **RemoteOK** requires keeping the original RemoteOK job URL and crediting "Remote OK" as the
  source (no logo reuse) — satisfied because the app only links out to `job.url` and labels the
  source. Its API returns a JSON array whose first element is a legal/metadata object (skipped).
- **Careerjet / Freelancer.com** carry their credential in the request URL / an auth header, so
  both sanitise error text to the exception type name only — never the key.

---

## Freelance & consulting (gigs)

The Danish consulting/freelance space is overwhelmingly login-, approval- or paid-gated. One read
API is wired (Freelancer.com); the rest are document-only.

| Name | What | DK relevance | Access | Status | Notes |
|---|---|---|---|---|---|
| Freelancer.com | Global project marketplace; official REST API | Global/remote gigs | free token (`FREELANCER_TOKEN`) | **Integrated** | `freelancer.py` — see the integrated table. |
| **Verama** (Ework Group) | Top Nordic independent-consultant broker; open assignments | Strong | **no-key public REST** | **Integrated** | `verama.py`. Re-probe found a genuine public feed at `GET https://app.verama.com/api/public/job-requests` (`public:true` records) — the earlier "login SPA" assessment was superseded. |
| **Hacker News** | "Freelancer? Seeking freelancer?" monthly threads | Remote/tech gigs | no-key (Algolia API) | **Integrated** | `hackernews.py` — see the integrated table. |
| **EU TED** (Tenders Electronic Daily) | DK public-sector IT/business **consultancy tenders** (CPV 72/79) | Strong (authoritative) | no-key public API | **Integrable (now, deferred)** | `POST https://api.ted.europa.eu/v3/notices/search` works keyless and live-returns Danish consultancy tenders (subsumes udbud.dk + Mercell). Deferred because these are procurement **RFPs you bid on**, not job postings (terse multilingual titles, no salary, company-bidder semantics) — would be wired as an explicitly-labelled "tenders" source on request. |
| **Brainville** | Nordic marketplace for freelance/consulting assignments + brokers (ex-Resrc) | Strong | paid + approval (Bearer Base64(`UserKey:SenderKey`)) | **Document-only** | API v2 is genuinely documented — `POST https://api.brainville.com/v2/market/search`. **But** the Market/Search endpoint needs a **paid** Premium subscription + Assignment-Export add-on **and** an approval-gated Sender Key (internal-use-only data). Buildable only for a user's own paid account. Captures Right People Group gigs transitively. |
| emagine (ex-ProData Consult) | Large IT/business consulting broker, HQ Copenhagen | Strong | login | Document-only | Re-probe found the real backend `portal-api.emagine.org`, but every job endpoint returns **HTTP 401** — the board requires auth. ProData now redirects to emagine and shares this gated portal. |
| Onsiter | Nordic contractor/consultant aggregator (~1000 assignments/day, DK confirmed) | Strong | scrape (Cloudflare 403) | Document-only | Index + `/api/assignments` are Cloudflare-403 to bots; detail pages public. No usable feed. |
| PeoplePerHour / Guru / Twine / Workana / Truelancer | Global freelance project marketplaces | Some–Minimal | scrape / login | Document-only | Re-probed live: no project RSS/JSON (feed URLs 404 or return HTML); listings are login- or scrape-only. |
| Braintrust / Gun.io / Wellfound / YunoJuno / Arc.dev / A.Team / Contra | Vetted / curated freelance & contract networks | Some | login (apply-to-join) | Document-only | Public pages show teaser roles only; the real job APIs are 401/session-gated behind account + screening. Contra's `/feed` + `/api/jobs` both 404. |
| 7N | Danish-origin elite IT consultancy/broker; agent-mediated | Strong | scrape (JS ATS) | Document-only | `jobs.7n.com` is a JS-rendered ATS shell; value is agent representation. |
| Right People Group | Copenhagen IT/management consulting broker | Strong | login / email alerts | Document-only | No public board/API. Its gigs flow into Brainville. |
| Worksome | Danish-origin Freelance Management System; vetted tech freelancers | Strong (the most DK-relevant freelance platform) | login + GraphQL (auth-only) | Document-only | Private client talent pools; GraphQL manages your own contracts, not open gigs. Create a profile to enter pools. |
| Malt (incl. merged Comatch) | Largest European freelance/consulting marketplace; Nordics covers DK | Some | profiles only (no public jobs API) | Document-only | Reverse marketplace — clients invite freelancers; only profiles are public. |
| Giig (`giig.dk`) | Danish freelancer platform (marketing/design/dev/IT) | Strong | login (profile/lead model) | Document-only | Companies push tasks to your inbox; no open-gig feed. |
| Upwork | Largest global freelance marketplace; GraphQL API | Global (weak DK) | free-key but OAuth2 3-legged | Document-only | Readable, but heavy 3-legged token flow + ToS limits on automated use. |
| Toptal | Closed vetted talent network (top ~3%) | Global | no public board/API | Document-only | Staff-matched; nothing to ingest. |
| Freelancermap | Pan-EU IT freelance projects; public Denmark list page | Some (DACH-centric) | scrape (HTML, no read API) | Document-only | Enterprise XML/JSON is import-only; no DK RSS verified. |
| Fiverr / Contra / Twago / Outvise / Useme / Expert360 / Catalant | Assorted freelance marketplaces | Minimal–Some | no API / login | Document-only | Wrong shape (gig supply not demand), login-gated, or no DK relevance. |

---

## Job boards (employee roles)

| Name | What | DK relevance | Access | Status | Notes |
|---|---|---|---|---|---|
| StepStone.dk | Major Danish general/professional board | Strong | no-key RSS | **Integrated** | `stepstonedk.py` — see above. |
| it-jobbank.dk / Jobindex.dk | DK IT board / DK's largest board | Strong | no-key RSS | **Integrated** | `itjobbank.py` / `jobindex.py`. |
| Jobfinder.dk / TechJob.dk | DK's largest engineer/IT/tech board (Ingeniøren) | Strong | scrape (jobs feed empty) | Document-only | `rss.xml` is an empty articles feed; jobs view has no RSS/JSON. Drupal HTML scrape only. |
| Jobsora / Talent.com (dk) / WhatJobs | Global aggregators with DK presence | Strong | partner / paid (inbound XML or CPC, token-by-request) | Document-only | Publisher-push / CPC-gated; no free outbound search/pull API. |

---

## Aggregators & remote

| Name | What | Relevance | Access | Status | Notes |
|---|---|---|---|---|---|
| Jobicy / RemoteOK / We Work Remotely / Working Nomads | Remote-jobs APIs/feeds | Remote, global | no-key | **Integrated** | See the integrated table. |
| Adzuna / Jooble / Careerjet / JSearch | Keyed aggregators | DK / global | free-key | **Integrated** | See the integrated table. |
| **Himalayas** | Large remote-jobs JSON API (~92k jobs), publicly advertised | Remote, global | no-key API | **Document-only** | Technically works (`GET https://himalayas.app/jobs/api?limit=20&offset=N`, clean JSON, robots.txt allows it). **But** its ToS §30 explicitly prohibits "data mining, robots, screen scraping, or similar automated data gathering … without Himalayas' prior written approval." To stay consistent with the project's ToS-friendly principle (same basis as ruling out EURES), it is **not integrated**. Revisit only with explicit written approval. |
| Findwork.dev | Tech-jobs search engine with a clean REST API | Minimal (incidental DK) | free token (`FINDWORK_TOKEN`) | **Integrable (optional key)** | `GET /api/jobs/` with `Authorization: Token <key>`. Tech-only, low DK yield — an optional complement. |
| EURES | EU cross-border public jobs portal incl. DK | Some | none (ToS forbids scraping) | Document-only | **Ruled out**: undocumented backend, ToS forbids automated extraction. DK state coverage is better via HR-Manager/SRL + Jobindex. |

---

## Academic & public sector

| Name | What | DK relevance | Access | Status | Notes |
|---|---|---|---|---|---|
| HR-Manager / SRL / Region Syddanmark | DK public-sector ATS (state + region) | Strong | no-key JSON | **Integrated** | `hrmanager.py` — generic, parameterised by `customer=` aliases. |
| University of Copenhagen (KU) | `employment.ku.dk` vacancies (academic + admin) | Strong | (no working no-key feed) | Document-only | KU runs on HR-Manager under customer `cid=3010` = the **already-queried SRL alias** (KU = DepartmentId 20019), but the public syndicated `incads=true` feed returns a fixed 25-item Jobindex subset that **excludes** KU postings, and the bare `ku` alias returns an empty `Items[]`. So no no-key alias surfaces KU jobs today; direct coverage would need scraping `employment.ku.dk/all-vacancies/?show=<id>` (out of scope). Partially covered in spirit via SRL. |
| EURAXESS Jobs (Denmark facet) | Pan-European research-jobs portal (postdoc/PhD/fellowships) | Strong | scrape (no read API/RSS) | Document-only | Only API is inbound XML submission; the DK-facet search is server-rendered HTML (fragile, ToS asks for politeness). |
| DTU (Technical University) | DTU vacancies on Oracle Recruiting Cloud | Strong | no-auth CE endpoint (host/site-specific) | Document-only | Oracle CE endpoint works unauthenticated but host + `siteNumber` are DTU-specific and fragile. |
| Akademikernes Jobbank (`jobbank.dk`) | DK's largest academic/graduate career board | Strong | RSS unconfirmed / scrape | Document-only | No verified RSS/XML/API (email jobagent only). Promote to integrable once a feed URL is confirmed. |
| Graduateland (now JobTeaser) | Copenhagen-founded student/graduate portal | Strong | login (SPA; 410 on listings) | Document-only | Login-walled SPA; no public feed. Partly mitigated: many roles also land on The Hub + HR-Manager. |
| Emply | Legacy DK public/uni/kommune ATS | Strong (shrinking) | per-tenant (fragmented) | Document-only | Being decommissioned → SRL on HR-Manager by end-2026. |
| Lederne / CA / aka.dk JobMatch | A-kasse / career-org member tools | Some–Strong | login / member-only | Document-only | Member-only CV-matching, not browsable boards. |

---

## Niche / staffing

| Name | What | DK relevance | Access | Status | Notes |
|---|---|---|---|---|---|
| Academic Work / Moment.dk / Adecco / Randstad (DK) | Staffing & temp agencies in DK | Strong | scrape (JS-heavy / no feed) | Document-only | No public API/RSS; listings JS-rendered or behind custom apps. Email jobagents only. |

---

## Investigated and excluded (not relevant platforms)

| Name | Finding |
|---|---|
| Bloffin | No such DK freelance platform; only unrelated "Bloffin Technologies". Skip. |
| Inhouse | Not a distinct platform; maps to in-house consultancies / Randstad Inhouse. Skip. |
| Ballou | Ballou PR — a tech PR agency, not a marketplace and not DK-based. Skip. |
| Comatch | Acquired by and fully merged into Malt (2022); covered by the Malt entry. |

---

## What to integrate next (priority order)

1. **University of Copenhagen (KU)** — would need a small `employment.ku.dk/all-vacancies` scraper
   (no working HR-Manager alias); medium effort, high DK-academic value.
2. **Findwork.dev** — optional keyed remote/tech complement; add behind a free token, off by default.
3. **Brainville** — the best DK *consulting/gig* source, but only worthwhile if the user obtains a
   paid, approved Brainville account (the spec is documented above and ready to build then).
4. **More HR-Manager customer aliases** (regions/kommuner that use HR-Manager) — each is a one-line
   addition to `hrmanager.py` once the public `customer=` alias is confirmed.

Everything else above is document-only by nature (login / partner / paid / ToS-restricted /
scrape-fragile) — kept here as the manual where-to-look list, not integration targets.
