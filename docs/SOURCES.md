# Job, consulting & freelance sources — full catalog

The definitive map of **every** job / freelance / consulting source researched for a Denmark-based
search (employee roles + remote + short-term/contract/tender work), whether or not it's wired into
the app. The live, wired sources are in [`jobfinder/sources/`](../jobfinder/sources/).

The catalog is organised by **access**, as requested:

- **[Part 1 — Non-gated](#part-1--non-gated-sources-no-api-key-no-login)** — usable with **no API key
  and no login** (a public RSS/JSON feed, ToS-permitting). The app's defaults live here.
- **[Part 2 — Gated](#part-2--gated-sources-api-key-login-approval-paid-or-scrape-only)** — everything
  that needs **an API key**, **a login/account**, **approval/payment**, is **ToS-restricted**, or is
  **scrape-only** (no machine-readable feed).

**Status:** **Integrated** = wired (a class in `jobfinder/sources/`) · **Integrable** = a clean
feed/key exists, buildable, not yet wired · **Document-only** = exists & relevant but not cleanly/
ethically ingestible (login/paid/ToS/scrape).

> **Ground rules:** Denmark-relevant first; nothing requiring login impersonation or violating a
> board's ToS is integrated (why Himalayas/EURES are document-only despite working); keyed sources
> resolve credentials from the secrets overlay, are skipped when unset, and never echo a key in an
> error. See [`SECURITY.md`](SECURITY.md) and [`ETHICS.md`](ETHICS.md).

---

## At a glance — 30 integrated sources

| Group | Sources |
|---|---|
| **DK (default on)** | The Hub · The Muse · it-jobbank · HR-Manager/SRL (state + Region Syddanmark + Region Hovedstaden) · Remotive · Arbeitnow |
| **DK (opt-in)** | StepStone.dk · Jobindex · **Universities — DTU/SDU (Oracle ORC)** · Adzuna* · Jooble* · Careerjet* |
| **Remote / EU / global (opt-in)** | Jobicy · RemoteOK · We Work Remotely · Working Nomads · Jobspresso · Authentic Jobs · **EU Remote Jobs** · **WeAreDevelopers** (DACH/pan-EU) · **Landing.jobs** (EU tech, salary) · **Findwork*** (tech/remote) · LinkedIn (guest) · JSearch* |
| **Consulting / gigs (opt-in)** | Verama · Hacker News · EU TED (tenders) · **Codeur** (FR projects) · Freelancer.com* |
| **Company boards (opt-in)** | ATS — Greenhouse/Lever/Ashby (Trustpilot, Too Good To Go, Veo, Corti, Pleo, Lunar, Planday, Netlight) |

`*` = needs a free API key. A **"Consulting / contract only"** search toggle filters every source
that exposes an employment type down to contract/freelance work.

---

## Part 1 — Non-gated sources (no API key, no login)

Public RSS/JSON feeds, usable without any credential.

### Denmark & Nordic

| Name | What | DK relevance | Status | Module / notes |
|---|---|---|---|---|
| The Hub (`thehub.io`) | Nordic startup/scale-up jobs (`countryCode=DK`) | Strong | **Integrated** (default) | `thehub.py` |
| The Muse | Curated listings filtered to DK cities | Some | **Integrated** (default) | `themuse.py` |
| it-jobbank.dk | DK's leading IT/tech board (StepStone family) | Strong | **Integrated** (default) | `itjobbank.py` |
| HR-Manager / SRL | DK public-sector ATS — Statens Rekrutteringsløsning (~140 state institutions) + **Region Syddanmark** + **Region Hovedstaden** | Strong | **Integrated** (default) | `hrmanager.py` — add more regions/kommuner as `customer=` aliases |
| StepStone.dk | Major DK general/professional board (StepStone/Jobindex RSS family) | Strong | **Integrated** (opt-in) | `stepstonedk.py` |
| Jobindex | DK's **largest** board (absorbed Ofir) | Strong | **Integrated** (opt-in) | `jobindex.py` |
| **DK universities — DTU, SDU** | Oracle Recruiting Cloud public REST (`recruitingCEJobRequisitions`) — academic/IT/admin, full descriptions | Strong | **Integrated** (opt-in) | `oracle.py` — generic over (host, siteNumber); add more DK orgs on Oracle |

### Remote / global

| Name | What | Relevance | Status | Module / notes |
|---|---|---|---|---|
| Remotive | Free remote-jobs JSON API | Remote, DK-eligible | **Integrated** (default) | `remotive.py` |
| Arbeitnow | Free European job-board JSON API | EU incl. DK | **Integrated** (default) | `arbeitnow.py` |
| Jobicy | Remote-jobs API, `geo=denmark` | Remote, DK-scoped | **Integrated** (opt-in) | `jobicy.py` |
| RemoteOK | Large global remote-jobs JSON API | Remote, global | **Integrated** (opt-in) | `remoteok.py` (keep URL + "Remote OK" credit) |
| We Work Remotely | Major remote board, RSS | Remote, global | **Integrated** (opt-in) | `weworkremotely.py` |
| Working Nomads | Curated remote-jobs JSON | Remote, global | **Integrated** (opt-in) | `workingnomads.py` |
| Jobspresso | Curated remote board (WP Job Manager `job_feed`) | Remote, contract mix | **Integrated** (opt-in) | `wpjobs.py` |
| Authentic Jobs | Remote design/dev board (WP `job_feed`) | Remote, contract mix | **Integrated** (opt-in) | `wpjobs.py` |
| **EU Remote Jobs** | EU-wide remote board (WP Job Manager `?feed=job_feed`) | EU remote | **Integrated** (opt-in) | `wpjobs.py` |
| **WeAreDevelopers** | Vienna/DACH/pan-EU tech board, public JSON API (~hundreds of thousands of listings) | EU tech, remote-filterable | **Integrated** (opt-in) | `wearedevelopers.py` |
| **Landing.jobs** | EU tech board, JSON `api/v1/jobs` (salary, relocation, country_code) | EU; remote/relocation | **Integrated** (opt-in) | `landingjobs.py` — company recovered from `/at/<slug>` URL; HTML blocks → `strip_html` |
| LinkedIn (guest) | Public `jobs-guest` search (no login) | Strong (geoId) | **Integrated** (opt-in) | `linkedin.py` — polite/low-volume |
| **4dayweek.io** | ~18k 4-day-week roles, JSON `api/jobs` (rich: salary, stack, lat/lon) | Global, EU coverage | **Integrable (no-key)** | undocumented internal feed; listings carry no canonical `url` (slug only) + niche (4-day-week) — left documented |

### Consulting / freelance gigs & tenders

| Name | What | Relevance | Status | Module / notes |
|---|---|---|---|---|
| Verama (Ework Group) | Public feed of open **consulting assignments** (fixed-term, rate, hours, dates) | Strong (Nordic incl. DK) | **Integrated** (opt-in) | `verama.py` — `app.verama.com/api/public/job-requests` |
| Hacker News | Monthly "Freelancer? Seeking freelancer?" threads (Algolia API) | Remote/tech gigs | **Integrated** (opt-in) | `hackernews.py` |
| EU TED | DK public-sector IT/business **consultancy tenders** (CPV 72/79) — limited-time projects you bid on | Strong (DK public) | **Integrated** (opt-in) | `ted.py` — labelled "tender"; subsumes udbud.dk + Mercell |
| **Codeur** | French freelance-**project** marketplace; public RSS of every newly-posted client gig | EU (FR; remote-deliverable) | **Integrated** (opt-in) | `codeur.py` — `/projects.rss`; anonymous clients, budget in description |

### Company boards (ATS)

| Name | What | Relevance | Status | Module / notes |
|---|---|---|---|---|
| Greenhouse / Lever / Ashby | Public no-key board APIs behind companies' own careers pages — **full descriptions** | Strong (named DK firms) | **Integrated** (opt-in) | `ats.py` — curated DK/Nordic list (Trustpilot, Too Good To Go, Veo, Corti, Pleo, Lunar, Planday, Netlight); extend via `JOBFINDER_ATS_COMPANIES` |

---

## Part 2 — Gated sources (API key, login, approval, paid, or scrape-only)

### 2a. Free API key (self-signup, no approval)

| Name | What | DK relevance | Status | Notes |
|---|---|---|---|---|
| Adzuna | Aggregator with a dedicated **Denmark** endpoint + salary | Strong | **Integrated** | `adzuna.py` · `ADZUNA_APP_ID`/`ADZUNA_APP_KEY` · supports `contract_type=contract` |
| Jooble | Job-search API covering Denmark | Strong | **Integrated** | `jooble.py` · `JOOBLE_API_KEY` · POST `type` filter for contract |
| Careerjet | Aggregator, Danish portal (`da_DK`) | Strong | **Integrated** | `careerjet.py` · free affiliate id |
| JSearch (RapidAPI) | Aggregates Google for Jobs (LinkedIn/Indeed/Glassdoor) | Query-scoped | **Integrated** | `jsearch.py` · `RAPIDAPI_KEY` (~200 free/mo) |
| Freelancer.com | Active short-term **gig** projects (official REST API) | Global gigs | **Integrated** | `freelancer.py` · free `FREELANCER_TOKEN` |
| Findwork.dev | Tech-jobs search engine, clean REST API | Moderate (remote/EU tech) | **Integrated** | `findwork.py` · `GET /api/jobs/` `Authorization: Token` · free `FINDWORK_TOKEN` |
| apijobs.dev | Global aggregator with `country=Denmark` filter | Potentially DK | **Blocked** | free key, but `api.apijobs.dev` serves a **self-signed TLS cert** — would require disabling cert verification (against egress posture). Re-check if they fix the cert |
| web3.career | Crypto/web3 jobs, single-endpoint API | Low (crypto niche) | **Integrable** | free token + attribution backlink required |
| Reed.co.uk | UK board, search API (Basic-auth key) | Low (UK-centric) | **Integrable** | free key; skip unless UK in scope |
| USAJobs.gov | US federal positions | None for DK | **Integrable** | free key; US-only — out of scope |

### 2b. Login / account required

| Name | What | DK relevance | Notes |
|---|---|---|---|
| Worksome | Danish FMS, vetted tech freelancers | Strong | login + auth-only GraphQL; private talent pools, no open gigs. *Create a profile.* |
| Graduateland (→ JobTeaser) | Copenhagen student/graduate portal | Strong | login-walled SPA; many roles also surface on The Hub + HR-Manager |
| Workindenmark / Jobnet (STAR) | Official DK govt portals | Strong | backed by STAR/Jobnet — certificate + signed agreement (MitID); no public feed |
| IDA · HK · Akademikernes / aka.dk · Lederne · PROSA | Union / a-kasse job banks | Some–Strong | member tooling + email job-agents; no public feed (content overlaps Jobindex) |
| emagine (ex-ProData) | Copenhagen IT-consulting broker | Strong | real backend `portal-api.emagine.org` returns **401** — auth required |
| Giig (`giig.dk`) | Danish freelancer platform | Strong | profile/lead inbox model; no open-gig feed |
| Right People Group | Copenhagen IT/mgmt consulting broker | Strong | login/email alerts; gigs flow into Brainville |
| Contra · Communo · Pangian | Freelance / remote communities | Some | login SPA / membership; `/feed`+`/api` 404 |
| Wellfound (AngelList) · Otta / Welcome to the Jungle · Honeypot / Talent.io | Startup / vetted / reverse-recruiting | Some | login + internal GraphQL; no public listings API |
| Upwork | Largest global freelance marketplace | Weak DK | GraphQL behind heavy 3-legged OAuth + ToS limits |
| Twago · Outvise | EU freelance/expert networks | Some–Minimal | login-gated, small footprint |

### 2c. Approval / partner / paid

| Name | What | DK relevance | Notes |
|---|---|---|---|
| Brainville | Nordic freelance/consulting marketplace | Strong | documented v2 API (`POST /v2/market/search`) but needs **paid Premium + approval-gated Sender Key**; internal-use-only data. Captures Right People Group transitively |
| Malt (incl. Comatch) | Largest EU freelance marketplace | Some | reverse marketplace — profiles only, clients invite |
| Toptal · Braintrust · Gun.io · YunoJuno · Arc.dev · A.Team | Vetted talent networks | Some | apply-to-join + screening; job APIs 401/session-gated |
| Expert networks — GLG · Guidepoint · Coleman · AlphaSights · Expert360 · Catalant | Consulting/expert engagements | Minimal | private, curated; no open feed |
| Talent.com · Jobsora · WhatJobs | Aggregators | Strong (coverage) | publisher-push / CPC partner / token-by-request — no free outbound pull |
| Emply (incl. AU, AAU partly) | Legacy DK uni/kommune ATS | Strong (shrinking) | public API needs an admin-issued **per-tenant** key; migrating to SRL by end-2026 |
| CVR / Virk | Danish company register | n/a (not jobs) | registered system-to-system access; company data, **no vacancies** |
| jobdataapi.com · Coresignal | Paid job-data aggregators | Some | paid tiers only |

### 2d. ToS-restricted (public API, but terms forbid automated use)

| Name | What | DK relevance | Notes |
|---|---|---|---|
| Himalayas | Large remote-jobs API (~87k, incl. Contractor/Freelance + salary) | Remote | API works, **but ToS §30 forbids automated data gathering without written approval** — held document-only (same basis as EURES/Reddit). Revisit only with approval |
| EURES | EU cross-border public jobs portal incl. DK | Some | undocumented backend; ToS forbids automated extraction. DK coverage better via HR-Manager + Jobindex |
| Reddit r/forhire (+ r/freelance) | `[Hiring]` gig posts | Some (remote) | the public `.json` is now edge-blocked (403); 2023 API terms require OAuth for automated use |

### 2e. Scrape-only / no machine-readable feed

These are real & relevant but expose no public RSS/JSON (HTML-only, SPA, Cloudflare, or expired/empty feeds). Listed as places to **search/apply manually**.

| Cluster | Sites | Notes |
|---|---|---|
| **DK boards** | Jobfinder.dk / TechJob.dk (Ingeniøren), Jobzonen.dk, Børsen Karrierelink / Finans.dk | feed/API paths 404; content largely overlaps Jobindex |
| **DK sector** | Sundhedsjobs.dk + danskesundhedsjobs.dk (health), Lærerjob.dk (teaching — feed is blog-only), Mediajob.dk / MediaWatch (media) | no jobs feed; Sundhedsjobs ingests via Emply only |
| **DK universities (no clean feed)** | KU + RUC (on HR-Manager but the JSON alias returns empty), AAU (CMS API 403) | KU/RUC need an `employment.ku.dk` scrape; AU/SDU/DTU covered (SDU/DTU via `oracle.py`) |
| **DK staffing** | Academic Work, Moment.dk, Adecco, Randstad, Hays / Michael Page / Robert Half | JS apps or internal AEM servlets; no public feed |
| **DK consulting brokers** | Onsiter (Cloudflare 403), 7N (JS ATS), Freelancermap | detail pages public but no usable feed |
| **Marketplaces** | PeoplePerHour, Guru, Twine, Workana, Truelancer, Fiverr, Useme | login/scrape; no public project feed |
| **Remote long-tail** | NoDesk, Remote.co, EuropeRemotely, Remoters, Outsourcely, Dynamite Jobs, Remote Talent, RubyNow (expired cert), ai-jobs.net, cryptocurrencyjobs.co, builtin.com, Remote3, EU-Startups | 403/Cloudflare/SPA/404 — no consumable feed |
| **EU freelance/contracting (DACH/FR/Nordic/UK)** | GULP, freelance.de, freelancermap (paid Enterprise XML), Expertlead, SOLCOM (geo-blocked), Westhouse, Proxify, Cinode, Talmix, Lemon.io, Gigster, Distributed, Malt, Twago, Outvise, Jobgether (empty stub), EuroTechJobs, eurojobs (inbound only), iAgora | login / WAF / Cloudflare / vetted-screening / paid / inbound-multiposting — no public read feed. The European freelance scene mirrors the Nordic one: marketplaces gate listings behind an account. |

---

## Investigated & excluded (defunct or not job platforms)

| Name | Finding |
|---|---|
| GitHub Jobs | Shut down 2021 (positions API removed). |
| Stack Overflow Jobs / Talent | Discontinued 2022. |
| Bloffin / Inhouse / Ballou | Not DK job/freelance platforms (cloud co / staffing concept / PR agency). |
| Comatch | Merged into Malt (2022) — see Malt. |
| CVR / Virk | Company register, not vacancies. |

---

## What to integrate next (priority order)

1. **More HR-Manager `customer=` aliases** — kommuner/regions on the same platform (one-line each once
   the public alias is confirmed; `regionh` just landed this way).
2. **More Oracle-ORC tenants** — other DK orgs on Oracle (the `oracle.py` class already parameterises
   host + siteNumber); confirm each tenant's host/`siteNumber`.
3. **University of Copenhagen (KU)** — needs an `employment.ku.dk/all-vacancies` scraper (no working
   HR-Manager alias).
4. **Brainville** — best DK consulting-gig source, but only if the user obtains a paid, approved account
   (spec recorded above).

Everything in Part 2b–2e is document-only by nature — kept here as the manual where-to-look list.
