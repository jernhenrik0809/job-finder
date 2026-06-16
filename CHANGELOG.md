# Changelog

All notable changes to Job Finder are documented here. Dates are YYYY-MM-DD.

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

### Tests
- 30 passing (added persistence round-trip / restart-survival, config, and draft-guardrail tests).

## [1.0.0] — 2026-06-09

Initial release: local CV → live-jobs matcher (LinkedIn guest + Remotive + Arbeitnow +
optional JSearch), explainable 0–100 scoring, and a review-first application-draft Outbox
(offline template + optional Claude). FastAPI + vanilla JS, GitHub Actions CI.
