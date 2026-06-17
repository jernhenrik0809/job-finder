# Changelog

All notable changes to Job Finder are documented here. Dates are YYYY-MM-DD.

## [1.19.0] — 2026-06-17

### Added — Background alerts + a notification inbox (opt-in)
- **Opt-in background checker** (`alerts.py`): a daemon thread that re-runs your saved searches on
  a schedule and raises in-app notifications for **new matches** and **follow-up reminders** (for
  applications that have gone quiet). Off by default; the interval is clamped to a polite 6-hour
  minimum so it never hammers the job boards. Toggle it (and the interval) in **⚙ Settings**, or
  set `JOBFINDER_ALERTS=1`.
- **In-app notification inbox** (`notifications.py`): a 🔔 bell in the top bar with an unread badge
  and a dropdown panel. New-matches items open that saved search; reminder items jump to the
  application. Notifications persist (SQLite schema **v4**, new `notifications` table) and are
  bounded.
- **CLI sweep**: `python -m jobfinder.alerts` runs a single check and exits — for people who'd
  rather drive it from the OS scheduler (cron / Task Scheduler) than keep the app running.
- New endpoints: `GET /api/notifications`, `POST /api/notifications/read`,
  `POST /api/notifications/{id}/read`, `DELETE /api/notifications/{id}`,
  `GET|POST /api/alerts/config`, `POST /api/alerts/run-now`.

### Privacy / safety
- **Fully local, in-app, no outbound delivery.** Alerts are an inbox you read in the app — nothing
  is emailed, toasted, or pushed anywhere. This keeps the "drafts/alerts never send" guarantee and
  the no-auto-submit invariant intact (no SMTP/IMAP is imported). The sweep contacts only the same
  job-board hosts a normal search does — no new egress.
- Migrated the FastAPI startup/shutdown hooks to the modern `lifespan` API (drops the deprecation
  warnings) and use it to start/stop the alerts thread cleanly.

### Fixed (from adversarial review)
- **Lost-update race:** the background sweep and the foreground `/run`·`/seen` endpoints did a
  non-atomic load→mutate→save on the same saved-search row. Added an atomic
  `Store.update_saved_search(id, mutator)` (single-lock read-modify-write) and routed all three
  call sites through it.
- **Unbounded duplicate reminders:** a reminder the user had *read* (but not dismissed) was
  re-created from scratch on every sweep. Dedupe now spans all reminders (read + unread) and
  refreshes the existing one in place (re-surfacing it as unread).
- **Mis-sorted refreshed reminders:** `save_notification`'s upsert now also refreshes the
  `created` column, so a refreshed reminder sorts and evicts by its new time.
- **Scheduler races:** a dedicated sweep lock serializes the scheduled sweep against a
  user-clicked "Check now" (no overlap, no `last_run` gate race); shutdown waits out an in-flight
  sweep (bounded) instead of returning after 2s.

### Tests
- 230 → 243 (sweep raises new-matches then is idempotent, skips a search with a missing CV,
  survives a failing source, reminder dedupe/refresh incl. the read-then-resurrect regression,
  atomic `update_saved_search`, prefs default-off + interval clamp + env default, scheduler
  interval gating, and the notifications + alerts-config + run-now API).

## [1.18.0] — 2026-06-17

### Added
- **Five new sources** (live-probed before building), broadening from Denmark to remote /
  short-term work — total **18**:
  - **StepStone.dk** — major Danish general/professional board (StepStone/Jobindex RSS family);
    no-key, `q=` keyword param, location/company parsed from the description HTML
    (`span.job-location` / `div.job-company`). **Opt-in.**
  - **RemoteOK** — large global remote-jobs JSON API (no key). Skips the leading legal/metadata
    array element; keeps the original RemoteOK job URL and credits "Remote OK" (its attribution
    terms). **Opt-in.**
  - **We Work Remotely** — major remote-jobs board via RSS (no key); `"Company: Role"` titles split
    on the first colon, location from `<region>`. **Opt-in.**
  - **Working Nomads** — curated remote-jobs JSON feed (no key). **Opt-in.**
  - **Freelancer.com** — active short-term **gig** listings via the official Projects REST API;
    free OAuth token (`FREELANCER_TOKEN` / ⚙ Settings), token sent in a header. **Opt-in, keyed.**
- The three no-key remote boards + StepStone.dk were verified live end-to-end (real jobs parsed);
  Freelancer.com is wired behind its free token, off until set.

### Researched but not added (documented in `docs/SOURCES.md`)
- **Himalayas** — a clean, publicly-advertised remote-jobs API that works technically, but its ToS
  §30 prohibits automated data gathering without written approval; left **document-only** to stay
  consistent with the ToS-friendly principle (same basis as EURES).
- **University of Copenhagen** — runs on HR-Manager under the already-queried SRL customer, but the
  syndicated feed excludes KU postings and no alias surfaces them; would need a small scraper.
- **Brainville** — the documented consulting-gig API is paid + approval-gated (confirmed); the full
  endpoint/auth/shape spec is recorded for if the user obtains a paid account.

### Security / privacy
- Host allow-list extended to `www.stepstone.dk`, `remoteok.com`, `weworkremotely.com`,
  `www.workingnomads.com`, `www.freelancer.com`; the runtime egress test exercises all five new
  sources; `freelancer_token` joins `SECRET_FIELDS` (auto-swept by the no-leak test). Freelancer's
  token rides in a request header, and its errors are sanitised to the exception type name.

### Tests
- 223 → 229 (StepStone.dk RSS + description-field parsing, RemoteOK legal-head skip + non-dict
  tolerance + salary/date mapping, We Work Remotely first-colon title split, Working Nomads array +
  non-dict tolerance, Freelancer token-required + parse + non-dict-project tolerance).

## [1.17.0] — 2026-06-17

### Added
- **Four new Danish job/consulting sources** (after a full-landscape research pass covering both
  employee roles *and* consulting/freelance gigs), bringing the total to **13**:
  - **it-jobbank** (`it-jobbank.dk`) — Denmark's leading IT/tech board (StepStone family), via its
    free no-login **RSS** feed (same parser shape as Jobindex; stdlib + BeautifulSoup, no new
    dependency). **On by default.**
  - **Public sector (HR-Manager / SRL)** — the recruitment ATS behind a huge share of DK
    public-sector, university and regional employers. One generic source queries a curated list of
    HR-Manager *customer* aliases: `statensrekrutteringsloesning_tr` (Statens Rekrutteringsløsning —
    ~140 Danish **state** institutions, a ToS-clean programmatic stand-in for the login-gated
    Jobnet/STAR) and `regionsyddanmark` (regional health). No-auth JSON; survives a single failing
    alias. **On by default.**
  - **Jobicy** — free, no-key remote-jobs JSON API scoped to Denmark-eligible roles
    (`geo=denmark`). **Opt-in.**
  - **Careerjet** — large aggregator with a Danish portal (`da_DK`, `careerjet.dk`); the strongest
    keyed *general-jobs* add for DK. **Opt-in, free affiliate id** (`CAREERJET_AFFID` / ⚙ Settings).
- Default no-key source set is now `remotive, arbeitnow, thehub, themuse, itjobbank, hrmanager` —
  all free and Denmark-relevant, with strong public-sector coverage out of the box.
- **[`docs/SOURCES.md`](docs/SOURCES.md)** — the definitive catalog of **every** researched Danish
  job + consulting/freelance source (integrated *and* not): integrable-next (StepStone.dk,
  Brainville, KU, Findwork, Freelancer.com) and document-only platforms (Worksome, Malt, Onsiter,
  Ework/Verama, 7N, EURAXESS, Graduateland, …), grouped by category with access type and status.
  Linked from the README.

### Security / privacy
- The security host allow-list was extended to the four new hosts (`www.it-jobbank.dk`,
  `api.hr-manager.net`, `jobicy.com`, `public.api.careerjet.net` + the Careerjet signup-doc host).
  Careerjet's affiliate id rides in its request URL, so its errors are sanitised to the exception
  **type name** only — never the key-bearing URL. The authoritative runtime egress-allow-list test
  now also exercises all four new sources, and the no-secret-in-responses sweep injects the
  `careerjet_affid` sentinel via env (covering the overlay-only secret).

### Fixed (from adversarial review)
- Hardened all four new parsers against the "one malformed record drops the whole source" class
  (the parse loop runs *after* `resp.json()`, outside the request try/except, so a single bad
  element would otherwise abort the batch): HR-Manager now skips non-dict `Items` and coerces a
  non-dict `Department` / `PositionLocation` / first `Advertisements` element (and tolerates
  `keywords`/`location` being `None`); Jobicy and Careerjet skip non-dict entries in their `jobs`
  arrays and coerce a non-string `date`/`pubDate` before slicing. This matches the codebase's
  existing convention (`themuse` already guards non-dict locations; `_strip_html` coerces with
  `str(...)`). The review's security and wiring dimensions came back clean.

### Tests
- 215 → 223 (it-jobbank RSS parsing, HR-Manager JSON + `/Date(…)/` parsing + one-failing-alias
  resilience, Jobicy JSON mapping, Careerjet affiliate-id requirement + parsing, plus three
  malformed-upstream robustness regressions covering the review fixes above).

## [1.16.0] — 2026-06-16

### Added
- **Three new Denmark job sources** (after researching the Danish landscape):
  - **The Hub** (`thehub.io`) — free, no-key JSON API of Nordic startup/scale-up jobs, filtered to
    `countryCode=DK` (≈360 current Danish roles, Copenhagen-heavy). **On by default.**
  - **The Muse** — free, no-key JSON API; queries the Danish cities and **filters client-side** to
    Denmark-located roles (its location filter is a global OR). **On by default.**
  - **Jobindex** — Denmark's **largest** job board, via its free, no-login, officially-promoted
    **RSS** feed (parsed with the stdlib + the already-present BeautifulSoup — no new dependency;
    handles the ISO-8859-1 feed and the "Title, Company" format). **Opt-in** (personal-use; also
    covers Ofir, now merged into Jobindex).
- Default sources are now `remotive, arbeitnow, thehub, themuse` — all free/no-key and
  Denmark-relevant. The security host allow-list was extended to the three new hosts.

### Researched but not added
- **Jobnet / STAR** (the official Danish public job database) requires partner onboarding (SOAP,
  contact STAR) and its search now sits behind MitID login — not self-serviceable. **EURES** only
  exposes an undocumented portal backend whose terms forbid automated extraction. **Careerjet** is
  DK-relevant (`da_DK`) but its ToS is conditional and needs a signup — a candidate for a future
  optional, key-gated source.

### Fixed (from review)
- Hardened the new parsers against malformed upstream data (the "silent source loss" class): The
  Muse no longer discards its whole result set if a `locations` entry is null/non-dict, and
  `_strip_html` coerces a non-string field instead of raising. The authoritative runtime
  egress-allow-list test now also exercises the three new sources.

### Tests
- 208 → 215 (The Hub mapping + keyword filter + non-string-description tolerance, The Muse
  Denmark-only filter + malformed-location tolerance, Jobindex RSS parsing incl. ISO-8859-1
  decoding + title split + location filter).

## [1.15.0] — 2026-06-16

### Added
- **Settings page (no more environment variables required).** A new **⚙ Settings** tab lets you
  paste your API keys — **Anthropic** (Claude writer), **RapidAPI** (JSearch), **Adzuna**, **Jooble**
  — and pick the **Claude model tier** (Opus / Sonnet / Haiku, with a per-letter cost hint), right
  in the app. Saving a key immediately lights up the matching source / the Claude option without a
  restart.
- Keys are kept in a **local, owner-only `secrets.json`** in the app data dir — **never** in the
  database, and the API only ever exposes whether a key is *set* (a boolean), never the value. An
  environment variable, if present, always wins (so existing setups are unchanged), and such fields
  are shown as **locked** in the UI. `jobfinder/secrets_store.py`; `GET/POST /api/settings`.

### Fixed (from review)
- The "saved" confirmation helper was scoped to the drawer, so saving in Settings threw a
  `ReferenceError` — showing a false error and (worse) skipping the re-gate, so a newly-added key
  didn't light up its source until reload. The helper is now module-scope; saving works and the
  source/Claude option activates immediately.

### Tests
- 202 → 208 (overlay env-precedence / persistence / clearing; Settings API sets a key, flips
  presence, and never returns the value; unknown-model rejected; env-locked surfaced).

## [1.14.0] — 2026-06-16

### Fixed (security)
- **API keys could leak into a search warning.** Adzuna and Jooble carry their key in the
  request URL (query param / path); on a network error the raised message embedded that URL,
  and `/api/search` returns source warnings in its JSON. Both now report only the error *type*
  (e.g. `Adzuna request failed (ConnectionError)`) — never the URL. *(Found by the review of the
  suite below.)*
- **Removed a stray third-party egress:** the page preconnected to `fonts.googleapis.com` while
  using a system-font stack — a pointless call to Google on every load. Deleted.

### Security
- **CI security-regression suite** (`tests/test_security_invariants.py`) — three core invariants
  enforced on every CI run:
  1. **No secret in any response** — sweeps every no-arg GET with sentinel keys loaded **and**
     drives the `/api/search` warning path (the one that leaked above); sentinels are derived
     from a single `config.SECRET_FIELDS`, so a new key is auto-covered.
  2. **No unexpected outbound host** — enforced at **runtime**: the network layer is patched to
     record every host each source actually contacts, so an `f"https://{host}"` can't slip past
     a source-text scan; backed by a cheap literal-string lint as a secondary check.
  3. **No auto-submit machinery** — an import smoke test (`smtplib`, `selenium`, `playwright`, …),
     anchored to import/call sites so a *comment* can't trip it; the real "drafts, never sends"
     guarantee is the design plus the runtime host allow-list.

### Tests
- 196 → 202.

## [1.13.0] — 2026-06-16

### Security / privacy
- **LLM-egress disclosure + PII redaction.** Job Finder is local-first; its *only* egress is the
  optional Claude path, which sends your CV text and the job description to Anthropic. The app now
  **says so** in the UI (next to *Use Claude*) and offers a **"redact contact details" toggle**,
  on by default, that masks **email / phone / links** in your CV (and style examples) *before* they
  are sent — your name is kept so the letter can still sign off, and dates / amounts / metrics are
  left intact. Applies to both the cover-letter and résumé-tailoring Claude paths.
- `jobfinder/privacy.py` (`redact_pii`); `redact_pii` flow on the generate / regenerate / tailor
  endpoints; `JOBFINDER_REDACT_PII` config default; `/api/draft-config` returns an `llm_egress`
  disclosure object. Nothing leaves the machine unless you enable Claude (needs an API key).

### Fixed (from review)
- The redactor now also catches **scheme-less profile/portfolio links** (`linkedin.com/in/jane`,
  `github.com/janedoe`, `janedoe.io/portfolio`) — previously only `http(s)://`/`www.` URLs were
  masked, so the most identifying link on a CV could leak. It still **keeps tech terms** that look
  like domains (`socket.io`, `ASP.NET`, `Node.js`), the **Danish 4-4 phone format** (`3122 8450`)
  is now masked, and **space-grouped amounts** (`25 000 000 DKK`) are no longer mistaken for a
  phone. The egress disclosure now also names uploaded **style examples**, and the UI reads the
  redaction toggle null-safely (a stale cached page can't break draft generation).

### Tests
- 188 → 196 (redactor masks email / phone incl. 4-4 split / bare profile URLs; keeps name, dates,
  space- and comma-grouped amounts, and domain-like tech terms; the Claude system prompt is
  verifiably scrubbed when enabled and untouched by default).

## [1.12.0] — 2026-06-16

### Added
- **Calibrated score bands.** The 0–100 score now has a defined, named meaning —
  **Strong** (≥65) · **Good** (≥40) · **Fair** (≥25) · **Weak** — shown on each match card (colour
  + label) and in the *Why?* header. Thresholds were calibrated against a labeled fixture set so
  the bands actually mean something.
- **Calibration fixture suite (regression guard).** A diverse, Denmark-relevant set of CV×JD
  fixtures (`tests/fixtures/calibration.json`), each job labeled *strong / partial / unrelated*,
  with assertions that run in CI: every strong match lands in the **Strong** band, unrelated roles
  stay out of the top bands, partials never reach **Strong**, and — for every CV — the
  **best-matching job is ranked on top**. This locks the scoring against silent drift as the
  matcher evolves. `score_band()` / `SCORE_BANDS` are the single source of truth (`matcher.py`),
  surfaced as `explanation.band` / `band_label`.

### Fixed (from review)
- The calibration tests now **derive** the band thresholds from `SCORE_BANDS` instead of
  duplicating them, and the "partial never reaches Strong" guard is anchored to the band *name* —
  so changing a threshold can't silently let a partial role read as a strong match.

### Tests
- 113 → 188 (band thresholds + 24 labeled fixtures × calibration assertions + per-CV monotonicity).
  Fixtures authored via a multi-agent workflow spanning six job domains.

## [1.11.0] — 2026-06-16

### Added
- **Ranking nudges + salary on cards.** The score now reflects more than text/skill/title overlap,
  using fields that were already fetched but ignored — as small, **bounded, never-penalizing**
  bonuses on top of the base score (a job can only score the *same or higher* than before, so the
  calibration never regresses):
  - **Freshly posted** (up to +1.5): recent postings get a lift; degrades safely to zero on an
    empty or non-ISO date (most sources), never crashing.
  - **Location / remote fit** (up to +0.5): matches your search location, or a *genuinely* remote
    role (trusted only from sources that report real per-job remote, not the ones that echo the flag).
  - **Seniority fit** (up to +0.5): a senior/lead CV matched to a senior/lead-titled role.
  Total bonus is hard-capped at **2.5 / 100**, so it only ever breaks near-ties — it can't override
  a decisive relevance gap. Every nudge is **explained**: it shows as a green **"Freshness & fit"**
  band in the *Why?* breakdown (its points still sum exactly to the score) with plain reasons, and
  **salary** is surfaced on the match card.
- `jobfinder/matcher.py` (`MatchConfig.today` / `search_location` / `search_remote`, threaded from
  the search settings in `engine.py`). Salary is **display-only** — never parsed into a score
  (cross-source salary strings aren't reliably numeric).

### Tests
- 105 → 113 (never-penalizing, points-still-sum-to-score with a nudge, recency bands + safe parsing
  of empty/garbage/full-datetime, future-date clamp, remote-source trust, location/seniority, salary
  display-only, 100-clamp). Design produced via a multi-agent map→design→synthesize workflow.

## [1.10.0] — 2026-06-16

### Added
- **Cover-letter guardrails (verified, not just promised).** Every letter — from either
  generator — is now checked offline and the findings are shown as badges in the application
  drawer:
  - **Placeholders**: an unresolved `[Company]` / `[Your Name]` means it isn't ready to send.
  - **Unsupported skill claims**: a skill the *job* wants that **isn't on your CV** (a gap skill)
    but is named in the letter is flagged, so you can frame it as something you're eager to learn
    rather than a claim. Scoping to the job's gap skills keeps this precise — ordinary prose like
    "express my interest" is never mistaken for a claim to know Express.js.
- `jobfinder/guardrails.py` (`check_letter`, the single home for the placeholder regex that
  `drafts.py` now imports). The application API responses carry a computed `guardrails` list.

### Fixed (from review)
- **High-precision skill check (no false accusations).** The unsupported-skill check now (1)
  excludes **soft skills and human languages** (prose-common, not CV credentials — "strong
  leadership" is never flagged), (2) requires a **possession cue** around the mention, so
  ordinary prose ("go above and beyond") and growth language ("eager to learn Kubernetes") are
  not flagged while real claims ("expert in Go", "Rust expertise") are, (3) **canonicalises**
  alias gap skills (`golang`→`go`) so a raw alias still matches, and (4) tolerates a malformed
  (non-string) skills list instead of 500-ing the applications list endpoint.
- `skills.skill_overlap` now canonicalises **both** sides, so a CV that lists `golang`/`k8s`
  matches a job's `go`/`kubernetes` instead of reporting them as gaps (also improves matching).

### Tests
- 94 → 105 (placeholder + legitimate-bracket guard; claim-context precision incl. prose, growth
  language, soft-skill exclusion, alias canonicalisation, non-string tolerance; API attaches
  guardrails on generate/get/patch/list).

## [1.9.0] — 2026-06-16

### Added
- **Confirm / edit your parsed profile.** The whole match funnel rests on the CV parser's
  guesses, so you can now fix them. The profile card has a **✎ Confirm / edit** toggle that opens
  inline controls: editable **skill chips** (remove with ×, add your own), plus your **name**,
  **target title(s)**, **location**, **years** and **seniority level**. Saving updates the stored
  profile, so your corrected skills and titles are what the next search scores against.
- API: `PATCH /api/profile/{cv_id}` (only provided fields change; lists are stripped/deduped,
  skills lowercased, years clamped 0–80; unknown `cv_id` → 404). `jobfinder/web.py`.

### Fixed (from review)
- Correcting your **title/skills** now also refreshes the **default search query**
  (`suggested_keywords`) — previously a search with an empty keyword box still queried the job
  boards with the parser's *original* wrong guess, defeating the point of the edit. Derivation is
  shared with `build_profile` via `cv_parser.default_query`.

### Tests
- 90 → 94 (corrections applied + persisted to the store, partial update, years clamp + 404,
  corrected title/skill refreshes the default query).

## [1.8.0] — 2026-06-16

### Security
- **Network-boundary hardening.** A personal app bound to `localhost` is still reachable by any
  website you visit — a malicious page can run `fetch('http://127.0.0.1:8000/api/...')` in the
  background and read your CVs and pipeline. Two always-on layers now guard the boundary:
  - **Host allow-list** (DNS-rebinding defense) — the request's `Host` must be a trusted name:
    loopback always, plus anything you declare in `JOBFINDER_ALLOWED_HOSTS` (and a concrete bind
    IP). A rebound attacker domain arrives as a non-allowed `Host` and gets a **400**. This is
    enforced **even when LAN serving is enabled** — enabling LAN only lets the server *bind* a
    public address; it never accepts an arbitrary `Host`.
  - **Same-origin** — any request whose `Origin` isn't same-origin with the host it targeted gets
    a **403** (ordinary cross-site CSRF). Your own page is unaffected; non-browser clients (curl,
    the test client) send no `Origin` and pass through.
  - **Won't bind beyond loopback by default**: `run.py` falls back to `127.0.0.1` (with a clear
    message) if asked to bind a public address without `--allow-lan` / `JOBFINDER_ALLOW_LAN=1`.
- `jobfinder/security.py` (`LocalSecurityMiddleware`, pure `check_request` + `build_allowed_hosts`).
  The Docker image sets `JOBFINDER_ALLOW_LAN=1` (a published container binds `0.0.0.0` by design);
  reach it via `http://localhost:8000` — the Host allow-list still applies, so add any other
  name/IP you'll use to `JOBFINDER_ALLOWED_HOSTS`.

### Tests
- 77 → 90 (`check_request` host/origin matrix incl. IPv6 loopback, userinfo/trailing-dot parsing,
  the **DNS-rebinding-blocked-even-with-LAN** regression, and live middleware allow/deny through
  the FastAPI test client).

## [1.7.0] — 2026-06-16

### Added
- **"Why this score?" explanation.** Every match card now has a **Why?** toggle that opens a
  transparent breakdown of its 0–100 score: a bar per component (**text similarity**,
  **skill overlap**, **title match**) showing each signal's strength and the **points it
  contributes** — and those points **sum exactly to the displayed score**. A short list of
  plain-English reasons (ordered by impact) explains the match, e.g. *"Matches 3 of your skills
  (Python, Django, AWS)"*. When a posting lists no recognisable skills, skill overlap is shown as
  **left out** (unknown), not scored as zero — and the remaining components re-normalise so the
  ceilings still sum to 100.
- `rank_jobs` now attaches a structured `explanation` object to each `Job`
  (`components` + `reasons` + `skills_detected`); `jobfinder/matcher.py`, surfaced via the
  existing search API and rendered in `static/app.js`.

### Changed
- CI actions bumped (`actions/checkout@v5`, `actions/setup-python@v6`) off the deprecated
  Node 20 runtime.

### Tests
- 73 → 77 (component points sum to the score, skills-omitted re-normalisation, reasons name
  matched skills, JSON round-trip through `Job.to_dict`).

## [1.6.1] — 2026-06-16

### Fixed (from review)
- **Wrong-type salary crash (Denmark sources).** A Jooble posting with a *numeric* salary
  (e.g. `45000` instead of `"45000 DKK"`) raised `AttributeError` on `.strip()` mid-loop,
  which took out the **entire** Jooble source (0 jobs + a warning) for that search — the same
  bug-class as the earlier null guards, but for wrong *types* rather than nulls. Adzuna had the
  analogous latent fragility: `int()` on a decimal-string salary (`"500000.0"`) raises
  `ValueError`. Both sources now coerce external fields defensively (`_s()` for strings,
  `int(float())` for salary figures), so a single odd field degrades to empty rather than
  wiping the source. `jobfinder/sources/jooble.py`, `jobfinder/sources/adzuna.py`.

### Tests
- 71 → 73 (Jooble numeric salary, Adzuna decimal-string salary — both assert the source survives).

## [1.6.0] — 2026-06-16

### Added
- **Denmark job sources.** Two free-key sources focused on the Danish market:
  - **Adzuna** — dedicated Denmark endpoint (`dk`, overridable via `JOBFINDER_ADZUNA_COUNTRY`);
    structured listings + salary. Needs free `ADZUNA_APP_ID` + `ADZUNA_APP_KEY`.
  - **Jooble** — covers Denmark; defaults the location to *Denmark* when none is given.
    Needs a free `JOOBLE_API_KEY`.
- Source checkboxes are now **generically key-gated**: any keyed source without its API key
  is disabled in the UI (`/api/sources` returns a `keyed` presence map). `jobfinder/sources/adzuna.py`,
  `jobfinder/sources/jooble.py`.

### Tests
- 68 → 71 (Adzuna/Jooble parsing with mocked Danish responses, Jooble Denmark-default).

## [1.5.0] — 2026-06-16

### Added
- **Résumé tailoring.** From an application's drawer, **Tailor résumé to this job** ranks
  *your own* CV bullets by relevance to the role (TF-IDF), each shown with **provenance**
  (the exact source line — this is selection + reordering, never fabrication), plus the
  **skills to emphasize** (matched) and **gaps** to address (missing). With a key, an optional
  **Claude rewrite** rephrases each bullet *grounded strictly in the original* (which is shown
  alongside so you can verify) — it is instructed never to add a fact not in your CV.
- `jobfinder/tailor.py`; API `POST /api/applications/{id}/tailor`. Skill-list lines are
  excluded from accomplishment bullets.

### Fixed (from review)
- The tailor result (including a paid Claude rewrite) now survives a drawer re-render — a
  status change or letter-regenerate no longer wipes it (cached client-side per application).
- The skills-list bullet filter no longer drops terse **verb-led** achievement bullets
  (e.g. "Built APIs, shipped features, led reviews").

### Tests
- 62 → 68 (bullet segmentation incl. skill-list + verb-led cases, relevance ranking +
  provenance, emphasize/gaps, mocked Claude rewrite, endpoint).

## [1.4.0] — 2026-06-16

### Added
- **Saved searches + new-match alerts.** Save any query (**★ Save this search**); the sidebar
  lists your saved searches with a **"N new"** badge. Clicking one runs it and loads the
  results into *Matches* with **NEW** flags on postings you haven't seen before, then marks
  them seen. **"check for new"** runs them all and refreshes the badges. New-match detection
  diffs each run's results against the ids already surfaced — no background scheduler, so the
  app stays a single off-friendly local process.
- `jobfinder/saved_searches.py`; SQLite **schema v3** (`saved_searches`); API
  `POST/GET /api/saved-searches`, `…/{id}/run`, `…/run-all`, `…/{id}/seen`, `DELETE …/{id}`.

### Fixed
- CV location detection no longer false-matches a skills line (e.g. "Skills: Python, Django")
  as a "City, Region" location.

### Tests
- 54 → 62 (saved-search model + diffing, store round-trip, run/seen/delete API, location guard).

## [1.3.0] — 2026-06-16

### Added
- **Insights dashboard** (new *Insights* tab) — a funnel
  (`saved → drafted → applied → interviewing → offer`) with stage-to-stage conversion,
  key metrics (applied, **response rate**, offers, **avg. time-to-response**),
  applications-by-source, and an 8-week "added per week" sparkline. All computed offline
  from your pipeline's event timelines — no telemetry.
- **Follow-up nudges** ("Needs attention"): applications sitting in *applied* for ≥7 days
  or *ready* for ≥3 days are surfaced; clicking one jumps to its pipeline card. No
  background scheduler — nudges are derived when you open the app.
- API: `GET /api/insights`; `jobfinder/insights.py` (`compute_insights`).

### Fixed (from review)
- Follow-up nudges for a *ready* draft are now anchored to **when the letter became ready**,
  not `updated` — editing a draft's notes no longer resets its age and suppresses the nudge.
- `avg_time_to_response` no longer drops apps that reached a response stage without an explicit
  *applied* step (it falls back to the pipeline-entry baseline), so it matches the response-rate
  population. Funnel "reached" semantics documented.

### Tests
- 44 → 54 (funnel math, response rate, time-to-response incl. no-explicit-applied, nudges incl.
  edit-survival regression, by-source, endpoint).

## [1.2.0] — 2026-06-16

The retention core from [`docs/ROADMAP.md`](docs/ROADMAP.md): the Outbox becomes a
tracked application pipeline.

### Added
- **Application pipeline / Kanban tracker.** Every job you pursue is now a durable
  **Application** with a lifecycle (`saved → drafting → ready → applied → screening →
  interview → offer → rejected/withdrawn`), an immutable **event timeline**, private
  **notes**, and the cover letter as its current artifact. New `jobfinder/applications.py`
  (state machine) + `applications` store table.
- **Kanban board UI** (the renamed *Pipeline* tab): drag a card between columns to change
  status; a **detail drawer** to edit the letter, add notes, regenerate, copy/download,
  and view the timeline.
- **＋ Save to pipeline** on match cards (save a role without drafting yet).
- **Regenerate** a letter from the stored job snapshot + CV (no re-search needed).
- API: `POST/GET /api/applications`, `GET/PATCH/DELETE /api/applications/{id}`,
  `POST /api/applications/{id}/regenerate`, `…/export`, `POST /api/applications/generate`.
  `set_status` validates transitions and logs events (replacing the old draft|ready whitelist).

### Changed
- The draft Outbox is superseded by the Application pipeline; generation now creates
  tracked applications instead of standalone drafts. `/api/drafts/*` → `/api/applications/*`.

### Fixed (from review)
- **Upgrade data-loss:** the SQLite v1→v2 migration is now real — it carries v1.x drafts
  forward into applications and bumps `schema_version` (previously a no-op that orphaned them).
- **Forward-compat:** stored rows are reconstructed via `from_dict` (unknown keys ignored), so
  one odd row can't 500 the whole pipeline.
- Defensive numeric coercion of an untrusted `job["score"]`; drag highlight no longer sticks;
  drawer no longer reopens if closed mid-request; deleting an application resets the match card's
  Save button.

### Tests
- 32 → 44 (Application state machine, store round-trip, pipeline API, v1→v2 migration,
  `from_dict` robustness).

## [1.1.0] — 2026-06-10

Foundations + the persistence hinge from [`docs/ROADMAP.md`](docs/ROADMAP.md) (Now phase).

### Added
- **Persistence.** Parsed CVs, style examples and the whole Outbox now persist in a
  local **SQLite** store and survive a restart (`jobfinder/store/`, default backend).
  Set `JOBFINDER_STORAGE=memory` for the old ephemeral behaviour.
- **Centralized config** (`jobfinder/config.py`) — one place for all environment
  settings (keys, model tier, storage, data dir, default sources, host/port).
- **`/api/health`** endpoint (used by the Docker healthcheck).
- **Docker**: `Dockerfile`, `.dockerignore`, `docker-compose.yml` (data on a `./data`
  volume; `docker compose up --build`).

### Changed
- **Default sources flipped to `remotive,arbeitnow`** (free/official); LinkedIn is now
  **opt-in**, honoring the ethics principle.
- **API state** moved out of `web.py` module-globals into the repository layer.
- **Claude drafting** model tier is now config-driven (`JOBFINDER_MODEL`); prompt
  hardened against fabrication, bracketed placeholders, and job-description prompt
  injection; leftover placeholders are flagged on the draft.

### Fixed
- **Plaintext-CV temp-file leak.** Uploaded CVs/examples are now parsed fully in memory
  (`BytesIO`) instead of a `NamedTemporaryFile(delete=False)` — a crash mid-parse can no
  longer leave a plaintext CV in the OS temp dir.
- **SQLite concurrency (from review).** Reads on the shared connection are now serialized
  by the same lock as writes — a concurrent read+write across FastAPI's threadpool could
  previously corrupt cursor state and 500. Hardened the placeholder detector against false
  positives, and extended the AI prompt-injection guard to the CV and style examples.

### Tests
- 32 passing (persistence round-trip / restart-survival, **concurrent read+write**, config,
  and draft-guardrail / placeholder-precision tests).

## [1.0.0] — 2026-06-09

Initial release: local CV → live-jobs matcher (LinkedIn guest + Remotive + Arbeitnow +
optional JSearch), explainable 0–100 scoring, and a review-first application-draft Outbox
(offline template + optional Claude). FastAPI + vanilla JS, GitHub Actions CI.
