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
2. **Searches live job boards** for matching roles:
   - **LinkedIn** — via the public, no-login guest job search (personal, low-volume use).
   - **Remotive** & **Arbeitnow** — free, no-key JSON APIs (remote / EU jobs).
   - **JSearch** (optional) — aggregates Google for Jobs incl. LinkedIn/Indeed/Glassdoor (needs a free RapidAPI key).
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

### Configuration (all optional, via environment variables)

| Variable | Default | What it does |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | Enables the **Claude** draft writer |
| `RAPIDAPI_KEY` | — | Enables the **JSearch** source |
| `JOBFINDER_MODEL` | `claude-opus-4-8` | Claude model tier (e.g. `claude-haiku-4-5` to cut cost) |
| `JOBFINDER_STORAGE` | `sqlite` | `sqlite` (persistent) or `memory` (ephemeral) |
| `JOBFINDER_DATA_DIR` / `JOBFINDER_DB` | OS app-data dir | Where the SQLite DB lives |
| `JOBFINDER_DEFAULT_SOURCES` | `remotive,arbeitnow` | Sources used when none are picked |
| `JOBFINDER_HOST` / `JOBFINDER_PORT` | `127.0.0.1` / `8000` | Bind address/port |

---

## Application drafts — the Outbox

Tick the roles you like in **Matches**, click **✍ Generate drafts**, and the app
writes a tailored cover letter for each into the **Outbox** tab. There you can
**edit, copy, download (.txt), regenerate, mark ready, or delete** each draft.

> **It drafts — it does not auto-submit.** Nothing is sent anywhere automatically.
> The Outbox stages drafts for *your* review; you copy/download and apply yourself.
> (Auto-submitting to LinkedIn would violate its ToS and risk your account.)

Two generators, mirroring the matching design:

| Mode | Needs a key? | Quality |
|------|:---:|---------|
| **Template** (default) | No | Solid, personalised from your CV + the job's matched skills. Instant, offline. |
| **Claude** (Opus 4.8) | Yes (`ANTHROPIC_API_KEY`) | Genuinely tailored prose that **learns your voice from uploaded example applications**. |

**Tone** (professional / warm / concise / enthusiastic) and **length** are adjustable.

**Style examples:** in the Outbox, upload a few of your past applications (PDF/DOCX/TXT).
The Claude generator uses them as a voice/style reference (the template generator
ignores them). To enable Claude:

```powershell
setx ANTHROPIC_API_KEY "sk-ant-..."     # open a NEW terminal afterwards
pip install anthropic
```

Without a key the app silently uses the offline template generator — the feature
works either way.

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
│  ├─ matcher.py          # hybrid 0–100 scoring
│  ├─ drafts.py           # application-draft generation (template + optional Claude)
│  ├─ data/skills.txt     # curated skills list (editable)
│  ├─ static/             # web UI (HTML/CSS/JS, no build step)
│  └─ sources/            # linkedin, remotive, arbeitnow, jsearch
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
