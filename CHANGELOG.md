# Changelog

All notable changes to Job Finder are documented here. Dates are YYYY-MM-DD.

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
