# Job Finder

[![tests](https://github.com/jernhenrik0809/job-finder/actions/workflows/ci.yml/badge.svg)](https://github.com/jernhenrik0809/job-finder/actions/workflows/ci.yml)

Upload your CV and get **ranked, live job matches** — scored against your actual
skills and experience. Runs entirely on your local PC with a clean web UI.

![steps](https://img.shields.io/badge/1-Upload%20CV-6c8cff) ![steps](https://img.shields.io/badge/2-Search-8b5cf6) ![steps](https://img.shields.io/badge/3-Ranked%20matches-34d399) ![steps](https://img.shields.io/badge/4-Draft%20Outbox-fbbf24)

> **Where this is headed:** see [`docs/VISION.md`](docs/VISION.md) for the full target-state vision (private local-first career co-pilot) and [`docs/ROADMAP.md`](docs/ROADMAP.md) for the phased plan (Now → Next → Later → Vision).

---

## What it does

1. **Reads your CV** (PDF / DOCX / TXT) and extracts your skills, job titles,
   seniority and years of experience.
2. **Searches live job boards** for matching roles — **28 sources**, the no-key Danish ones
   **on by default**, broadening to remote / short-term / consulting work across Europe:
   - **Denmark:** **it-jobbank** & **Public sector (HR-Manager / SRL)** (default) — DK's leading IT
     board plus the public-sector backbone: one feed spans ~140 Danish **state** institutions
     (Statens Rekrutteringsløsning) + Region Syddanmark + Region Hovedstaden; **The Hub** & **The
     Muse** (default; DK startups / Denmark-located roles); **StepStone.dk** & **Jobindex** (opt-in
     RSS — Jobindex is DK's largest, also covers Ofir); **Universities** (opt-in; DTU & SDU via their
     public Oracle Recruiting Cloud APIs); **Adzuna**, **Jooble** & **Careerjet** (free-key, strong DK).
   - **Remote / global:** **Remotive** & **Arbeitnow** (default), plus **Jobicy**, **RemoteOK**,
     **We Work Remotely**, **Working Nomads**, **EU Remote Jobs** & **WeAreDevelopers** (DACH/pan-EU
     tech) — opt-in, no-key remote boards.
   - **Company boards (ATS):** **Greenhouse / Lever / Ashby** — the public, no-key APIs behind
     companies' own careers pages, giving **full job descriptions** straight from a curated list of
     Danish/Nordic firms (Trustpilot, Pleo, Corti, Lunar, Veo, Too Good To Go…). Opt-in; extend the
     list with `JOBFINDER_ATS_COMPANIES`.
   - **Consulting / freelance gigs:** **Verama** (Ework Group's public consultant-assignment feed —
     fixed-term contracts with rate & hours, no key), **Hacker News** "Seeking freelancer" monthly
     threads (no key), **EU TED** (Danish public-sector IT/consultancy **tenders** — limited-time
     projects, no key), **Codeur** (French freelance-project marketplace, no key), **Jobspresso** &
     **Authentic Jobs** (remote/contract boards, no key), and **Freelancer.com** (official API, free
     token). All opt-in.
   - **Consulting / contract only:** a search toggle that keeps just contract/freelance work across
     every source that exposes an employment type — turning the app into a **job board for a
     consultant**.
   - **JSearch** (optional) — aggregates Google for Jobs incl. LinkedIn/Indeed/Glassdoor (free RapidAPI key).
   - **LinkedIn** — via the public, no-login guest job search (opt-in; personal, low-volume use).

   👉 **The full catalog** of every job + consulting/freelance source we researched — wired *and*
   not-yet-wired (Brainville, Worksome, Himalayas, university/EURAXESS feeds, and more), each with
   its access type and integration status — is documented in [`docs/SOURCES.md`](docs/SOURCES.md).
3. **Scores every job 0–100** against your CV using a transparent hybrid of
   text similarity (TF-IDF), skill overlap, and job-title match — and shows you
   exactly **which skills you have** and **which you're missing** for each role.
4. **Drafts tailored applications** for the roles you pick, into a review-first
   **Outbox** (see below).

Everything runs offline except the (optional) live job fetching. No data leaves
your machine; there is no account or login.

---

## Quick start (Windows)

Just double-click **`start.bat`**. On first run it creates a virtual environment,
installs dependencies, and opens the app in your browser at
<http://127.0.0.1:8000>.

### Manual start (any OS)

```bash
pip install -r requirements.txt
python run.py --open
```

Then open <http://127.0.0.1:8000>. Drop in your CV, tweak the search, and hit
**“Find matching jobs.”**

> **Tip:** LinkedIn is the slowest source (it politely throttles requests and
> fetches each job's full description), taking ~20–60s. Remotive/Arbeitnow are
> the **default** (near-instant); LinkedIn is **opt-in** — tick it when you want it.

### Run with Docker

```bash
docker compose up --build      # → http://localhost:8000
```

Your data (the SQLite store) persists in `./data` on the host. To enable the AI
draft writer / JSearch source, uncomment `ANTHROPIC_API_KEY` / `RAPIDAPI_KEY` in
`docker-compose.yml`.

### Your work is saved

Parsed CVs, style examples and the whole Outbox are stored in a local **SQLite**
database, so they **survive a restart**. By default it lives at
`%LOCALAPPDATA%\JobFinder\jobfinder.db` (Windows) / `~/.local/share/jobfinder/`
(Linux/macOS). Nothing is uploaded anywhere.

### Configuration

API keys and the Claude model tier can be set **in the app** — open the **⚙ Settings** tab and
paste them (Anthropic, RapidAPI/JSearch, Adzuna, Jooble, Careerjet, Freelancer.com). They're saved to a local owner-only file
(never the database, never echoed back), and the matching source / Claude option lights up
immediately. Everything below also works as **environment variables**, which take precedence:

| Variable | Default | What it does |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | Enables the **Claude** draft writer |
| `RAPIDAPI_KEY` | — | Enables the **JSearch** source |
| `ADZUNA_APP_ID` / `ADZUNA_APP_KEY` | — | Enables the **Adzuna** source (free key at developer.adzuna.com) |
| `JOBFINDER_ADZUNA_COUNTRY` | `dk` | Adzuna country (Denmark by default; e.g. `gb`, `de`, `se`) |
| `JOOBLE_API_KEY` | — | Enables the **Jooble** source (free key at jooble.org/api/about) |
| `CAREERJET_AFFID` | — | Enables the **Careerjet** source (free affiliate id at careerjet.com/partners/api) |
| `FREELANCER_TOKEN` | — | Enables the **Freelancer.com** gigs source (free OAuth token at freelancer.com/api/docs) |
| `JOBFINDER_ATS_COMPANIES` | (curated DK list) | Company boards to query, as `provider:token` (e.g. `greenhouse:trustpilot,ashby:Pleo,lever:veo`) |
| `JOBFINDER_MODEL` | `claude-opus-4-8` | Claude model tier (e.g. `claude-haiku-4-5` to cut cost) |
| `JOBFINDER_STORAGE` | `sqlite` | `sqlite` (persistent) or `memory` (ephemeral) |
| `JOBFINDER_DATA_DIR` / `JOBFINDER_DB` | OS app-data dir | Where the SQLite DB lives |
| `JOBFINDER_DEFAULT_SOURCES` | `remotive,arbeitnow,thehub,themuse,itjobbank,hrmanager` | Sources used when none are picked |
| `JOBFINDER_HOST` / `JOBFINDER_PORT` | `127.0.0.1` / `8000` | Bind address/port |
| `JOBFINDER_ALLOW_LAN` | `0` | Permit *binding* beyond loopback (see **Privacy & network safety**) |
| `JOBFINDER_ALLOWED_HOSTS` | — | Extra `Host` names/IPs the server answers to (comma-separated) |
| `JOBFINDER_REDACT_PII` | `true` | Mask contact details in your CV before the optional Claude send |
| `JOBFINDER_ALERTS` | `false` | Turn on the opt-in background saved-search checker (also toggleable in ⚙ Settings) |
| `JOBFINDER_ALERTS_INTERVAL_HOURS` | `6` | How often the background checker runs (clamped to a 6-hour minimum) |

---

## Privacy & network safety

Your CVs, cover letters and pipeline are stored locally and never uploaded. Because the app
runs a small web server on your machine, it also guards that boundary:

- **Same-origin only.** A web page you visit in another tab could otherwise quietly call
  `http://127.0.0.1:8000/api/...` and read your data. Job Finder rejects any cross-site request
  (CSRF), so only its own page can talk to the API.
- **Host allow-list (anti DNS-rebinding).** It only answers requests addressed to a name it
  trusts — `localhost`/`127.0.0.1` by default — so a rebound attacker domain can't reach the API.
- **Loopback by default.** It binds `127.0.0.1` and refuses to serve the wider network unless you
  ask. To use it from your phone or another computer on a **trusted** network, start it with
  `python run.py --allow-lan --host 0.0.0.0` (or set `JOBFINDER_ALLOW_LAN=1`) **and** declare the
  address you'll connect to in `JOBFINDER_ALLOWED_HOSTS` (e.g. `JOBFINDER_ALLOWED_HOSTS=192.168.1.50`).
  You'll see a warning, because anyone on that network can then reach it with no login.
- **One disclosed egress, minimised.** The *only* time data leaves your machine is if you turn on
  the optional **Claude** writer (needs your own API key): it sends your CV text and the job
  description to Anthropic. The UI says so, and a **"redact contact details"** toggle (on by default)
  strips email / phone / links from your CV before sending — your name stays so the letter can sign
  off. With no key set, nothing is ever sent.

For the full picture, see [`docs/PRIVACY.md`](docs/PRIVACY.md) (what's stored and what leaves),
[`docs/SECURITY.md`](docs/SECURITY.md) (threat model + protections), and
[`docs/ETHICS.md`](docs/ETHICS.md) (drafts-never-submits, no fabrication, personal-use principles).

---

## Applications — the Pipeline (Kanban tracker)

Every job you pursue becomes a tracked **Application** on a Kanban board, so your
search survives across weeks — not just one session.

- In **Matches**, hit **＋ Save to pipeline** on any card (saved, no letter yet), or
  tick several roles and **✍ Draft applications** to create them *with* a tailored
  cover letter.
- The **Pipeline** tab is a board with a column per stage:
  **saved → drafting → ready → applied → screening → interview → offer → rejected / withdrawn**.
  **Drag a card** between columns to update its status (each move is logged on the
  card's timeline; entering *applied* stamps the date).
- **Click a card** to open its drawer: edit the cover letter (subject + body), add
  private **notes**, **regenerate** the letter, **copy / download**, see the
  **timeline**, or delete.

> **It drafts and tracks — it never auto-submits.** Nothing is sent anywhere
> automatically. You review, copy/download, and apply yourself. (Auto-submitting to
> LinkedIn would violate its ToS and risk your account.)

**Guardrails on every letter.** The drawer checks each draft offline and flags two things, so
"it never fabricates" is *verified*, not just promised: unresolved **placeholders** (`[Company]`,
`[Your Name]`) that mean it isn't ready to send, and any **skill the job wants that isn't on your
CV** but appears in the letter — so you can frame it as something you're keen to learn rather than
a claim. (It's scoped to the role's gap skills, so ordinary prose isn't mistaken for a claim.)

Everything in the pipeline persists locally (SQLite), so it's all still there when
you reopen the app.

Two cover-letter generators, mirroring the matching design:

| Mode | Needs a key? | Quality |
|------|:---:|---------|
| **Template** (default) | No | Solid, personalised from your CV + the job's matched skills. Instant, offline. |
| **Claude** (Opus 4.8) | Yes (`ANTHROPIC_API_KEY`) | Genuinely tailored prose that **learns your voice from uploaded example applications**. |

**Tone** (professional / warm / concise / enthusiastic) and **length** are adjustable.

**Style examples:** in the Pipeline tab, upload a few of your past applications (PDF/DOCX/TXT).
The Claude generator uses them as a voice/style reference (the template generator
ignores them). To enable Claude:

```powershell
setx ANTHROPIC_API_KEY "sk-ant-..."     # open a NEW terminal afterwards
pip install anthropic
```

Without a key the app silently uses the offline template generator — the feature
works either way.

---

## Insights

The **Insights** tab turns your pipeline into a funnel
(`saved → drafted → applied → interviewing → offer`) with stage-to-stage conversion,
your **response rate**, average **time-to-response**, applications-by-source, and a
weekly trend — all computed locally from your own data. A **Needs attention** list
nudges you to follow up on applications that have gone quiet (applied ≥7 days ago, or
drafted but not sent).

---

## Résumé tailoring

Open any application in the **Pipeline** and click **✨ Tailor résumé to this job**. It ranks
*your own* CV bullets by how well they fit the role, shows the **skills to emphasize** and the
**gaps** to address, and — crucially — every bullet is shown with its **provenance** (the exact
line from your CV). It selects and reorders your real experience; it never invents anything.
With an `ANTHROPIC_API_KEY` set, an optional **Claude rewrite** rephrases each bullet for the
job, grounded strictly in your original (shown alongside to verify).

---

## Saved searches

Click **★ Save this search** to store a query. Your saved searches live in the sidebar
with a **"N new"** badge; click one to re-run it — postings you haven't seen are flagged
**NEW** — or hit **check for new** to refresh every badge at once. It's how you catch new
roles without re-typing the same search.

### Background alerts (opt-in)

By default searches run only when you ask. If you'd like the app to watch for you, turn on
**Background alerts** in **⚙ Settings**: it re-runs your saved searches on a schedule (every
6 / 12 / 24 hours) and drops **new matches** — plus **follow-up reminders** for applications
that have gone quiet — into the **🔔 inbox** in the top bar. Click a new-matches notification
to open that search; click a reminder to jump to the application.

It's **fully local and in-app** — nothing is ever emailed or pushed anywhere; the app performs
no outbound delivery. Prefer not to leave the app running? Run a single sweep from your OS
scheduler (cron / Task Scheduler) instead:

```bash
python -m jobfinder.alerts      # run one check and exit
```

---

## Confirm your profile

Parsing a CV is heuristic — a skill can be missed, a title mis-read. After uploading, click
**✎ Confirm / edit** on the profile card to fix it: add or remove **skills**, set your **target
title(s)**, **location**, **years** and **seniority**. Your corrections are saved and used for
the next search, so a single fix lifts every match. (It's the cheapest way to improve results.)

---

## How matching works

Each job gets a 0–100 score:

```
score = 0.55 · text_similarity     (TF-IDF cosine: your whole CV vs the posting)
      + 0.30 · skill_overlap       (your skills ∩ the job's required skills)
      + 0.15 · title_match         (your target title vs the job title)
```

- Scores are **absolute**, not relative to the batch — a genuinely strong match
  scores high whether or not better jobs are present, and weak matches stay low.
- Skill overlap is **recall-oriented** and capped so a verbose posting listing 30
  skills doesn't unfairly penalise a strong candidate.
- If a posting has no recognisable skills, that component is dropped (not guessed),
  so unrelated jobs aren't inflated.

On top of that base, a few **bounded, never-penalizing nudges** (max **+2.5** total) lift jobs
that are a better real-world fit: **freshly posted**, a **location / genuine-remote** match, or a
**seniority** match to your level. They only ever break near-ties — never enough to override a
decisive relevance gap — and each one is shown as a green band in the **Why?** breakdown. (Salary
is shown on the card but never scored — cross-board salary text isn't reliably comparable.)

The final score is shown as a **calibrated band** — **Strong** (≥65) · **Good** (≥40) ·
**Fair** (≥25) · **Weak** — so a number has a consistent meaning. Those thresholds aren't guessed:
a labeled set of CV×JD fixtures (real-style strong / partial / unrelated pairs across several job
fields) is checked in CI to make sure strong matches keep landing in **Strong**, unrelated roles
stay low, and the best-matching job for any CV is always ranked on top.

### Why this score? (transparent breakdown)

Every match card has a **Why?** toggle. It opens a breakdown showing each component's
strength and the **points it contributes** — and those points **sum exactly to the score** —
plus a few plain-English reasons (*"Matches 3 of your skills (Python, Django, AWS)"*,
*"Title matches your target 'Backend Engineer'"*). When a posting lists no recognisable
skills, skill overlap is shown as *left out* (unknown) rather than counted as zero, and the
other components re-normalise to fill the 100. Nothing about the score is hidden.

### Optional: semantic matching

For meaning-aware matching (e.g. "ML" ≈ "machine learning"), install the extra:

```bash
pip install sentence-transformers
# CPU-only torch (smaller): pip install torch --index-url https://download.pytorch.org/whl/cpu
```

Then tick **“Semantic match”** in the UI. It transparently falls back to TF-IDF
if not installed. The first run downloads a ~90 MB model (`all-MiniLM-L6-v2`).

---

## Optional: enable JSearch (LinkedIn-comparable, reliable)

Get a free key at [RapidAPI → JSearch](https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch)
(~200 requests/month free), then set it once:

```powershell
setx RAPIDAPI_KEY "your-key-here"     # open a NEW terminal afterwards
```

The **JSearch** source then becomes selectable in the UI.

---

## Project layout

```
Job finder/
├─ run.py                 # launcher (python run.py --open)
├─ start.bat              # one-click Windows launcher
├─ requirements.txt
├─ jobfinder/
│  ├─ web.py              # FastAPI backend + JSON API
│  ├─ engine.py           # orchestration: CV → search → dedup → rank
│  ├─ cv_parser.py        # PDF/DOCX/TXT → text → structured profile
│  ├─ skills.py           # skill extraction (curated dictionary, word-boundary)
│  ├─ matcher.py          # hybrid 0–100 scoring + per-job "why this score" explanation
│  ├─ security.py         # same-origin + loopback network-boundary guard
│  ├─ drafts.py           # application-draft generation (template + optional Claude)
│  ├─ data/skills.txt     # curated skills list (editable)
│  ├─ static/             # web UI (HTML/CSS/JS, no build step)
│  └─ sources/            # 28 sources + normalize.py (see docs/SOURCES.md for the full catalog)
└─ tests/                 # pytest unit tests + sample CV
```

## Running the tests

```bash
pip install pytest
python -m pytest tests/ -q
```

---

## Notes & limits

- **LinkedIn** uses public guest pages only — no login, no fake accounts. It is
  intended for **personal, low-volume** searching. The endpoint is undocumented
  and throttles after ~10 pages from one IP; the app keeps requests small, adds
  polite randomised delays, and falls back to the other sources if blocked.
- **Scanned / image-only PDFs** have no text layer — the app detects this and
  asks you to paste your CV text instead (no OCR is bundled).
- Free fallback APIs (Remotive/Arbeitnow) are remote/EU-leaning; use LinkedIn or
  JSearch for the broadest, location-specific coverage.

This is a personal tool. Be respectful of every job board's terms of service.
