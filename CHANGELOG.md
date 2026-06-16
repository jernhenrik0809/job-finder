# Changelog

All notable changes to Job Finder are documented here. Dates are YYYY-MM-DD.

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
