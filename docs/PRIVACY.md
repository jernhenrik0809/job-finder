# Privacy

Job Finder is **local-first**: your data lives on your machine and is not uploaded,
shared, or used for analytics. There is no account, no login, and no telemetry.

## What's stored, and where

| Data | Where | Notes |
|---|---|---|
| Parsed CVs, style examples, applications/pipeline, saved searches | A local **SQLite** database at `%LOCALAPPDATA%\JobFinder\` (Windows) / `~/.local/share/jobfinder/` (Linux/macOS), or `./data` under Docker | Survives restarts; never leaves your machine. Override with `JOBFINDER_DATA_DIR` / `JOBFINDER_DB`, or use `JOBFINDER_STORAGE=memory` for an ephemeral, nothing-on-disk run. |
| API keys (Anthropic, RapidAPI, Adzuna, Jooble) | Environment variables, **or** a local owner-only `secrets.json` in the data dir (set from the **⚙ Settings** page) | Never written to the application database and never returned in any API response — only their *presence* is exposed (enforced in CI). Environment variables take precedence. |

Uploaded CV files are parsed **in memory** and never written to a temporary file, so a
crash can't leave a plaintext CV on disk.

## Network activity

- **Job search** sends only your *search query* (keywords, location) to the job boards
  you select — never your CV. The free sources (Remotive, Arbeitnow) need no key; the
  others (Adzuna, Jooble, JSearch, LinkedIn) are opt-in.
- **Claude drafting / tailoring** (optional, needs `ANTHROPIC_API_KEY`) is the only path
  that sends your CV. When enabled it sends your CV text, any uploaded style examples, and
  the job description to **Anthropic**. The UI discloses this next to *Use Claude*, and a
  **redact contact details** toggle — **on by default** — strips email, phone numbers and
  links from your CV (and examples) first. Your name is kept so the letter can sign off;
  dates, amounts and metrics are preserved. Set `JOBFINDER_REDACT_PII=false` to change the
  default.
- Nothing else is sent anywhere. The UI loads no third-party fonts, scripts, or trackers.

## Your data rights

It's your machine: to delete everything, stop the app and remove the SQLite database (the
data dir above), or run with `JOBFINDER_STORAGE=memory`. Individual CVs, applications and
saved searches can be deleted from the UI.
