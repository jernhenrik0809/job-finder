# Ethics

Job Finder is built to help an individual run their own job search well — not to automate
mass-applying, scrape at scale, or deceive employers. These principles are load-bearing;
several are enforced in code and CI.

## Principles

1. **It drafts; it never submits.** Job Finder generates cover letters and tailored
   résumé content into a review-first pipeline. *You* review, edit, and apply yourself.
   It never auto-submits an application or sends an email on your behalf. (A CI smoke test
   blocks SMTP / browser-automation imports; the design has no submit path.)

2. **No fabrication.** Generated letters are grounded only in your real CV. The offline
   guardrails flag unresolved placeholders and any skill a posting wants that isn't on
   your CV but appears in the letter — so "never fabricates" is *verified*, not just
   promised. Résumé tailoring only selects and reorders your real bullets (with
   provenance); the optional Claude rewrite is instructed never to add a fact you didn't
   write.

3. **Personal, low-volume use of public sources.** The LinkedIn source uses only the
   public, no-login guest job-search pages, with realistic pacing and polite delays, and
   falls back to other sources if throttled. It is intended for personal searching — not
   bulk scraping, fake accounts, or evading rate limits. Auto-submitting to LinkedIn would
   violate its ToS and risk your account, so the app does not.

4. **Local-first, no telemetry.** Your data stays on your machine; nothing is uploaded for
   analytics. The single optional egress (Claude) is disclosed and minimisable. See
   [PRIVACY.md](PRIVACY.md).

5. **Transparent scoring.** The 0–100 match score is explainable (every component and
   nudge is shown) and calibrated against a labeled fixture set, so it can't silently
   mislead you about how well you fit a role.

## Respect the job boards

Each source has its own Terms of Service. Use the sources responsibly, keep volume
personal, and prefer the sanctioned APIs (Adzuna, Jooble, JSearch, Remotive, Arbeitnow)
over scraping where you can.
