"""FastAPI backend serving the Job Finder UI and JSON API.

State lives in a Store (memory or SQLite) behind the repository interface — not in
module-global dicts — so the pipeline and parsed CVs survive a restart when the SQLite
backend is active (the default). The durable unit is the Application (a tracked job in
your pipeline); a generated cover letter is its current artifact.
"""
from __future__ import annotations

import secrets
import time
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import __version__
from .applications import (
    STATUSES, SUGGESTED_NEXT, attach_letter, job_snapshot, new_application, set_status,
)
from .config import settings
from .cv_parser import CVProfile, build_profile, default_query, extract_text_from_bytes, looks_empty
from .drafts import DraftOptions, generate_draft, llm_available
from .engine import SearchSettings, find_jobs
from .guardrails import check_letter
from .insights import compute_insights
from .saved_searches import new_saved_search, register_run, mark_seen
from .security import LocalSecurityMiddleware, build_allowed_hosts
from .sources import available_sources
from .store import get_store
from .tailor import generate_tailoring

app = FastAPI(title="Job Finder", version=__version__)

# Network-boundary hardening: reject cross-site (CSRF) requests and any Host not on
# the allow-list (DNS-rebinding defense), so a stray browser tab can't read the
# user's CVs/letters. Loopback is always accepted; the user adds LAN names/IPs via
# JOBFINDER_ALLOWED_HOSTS. A concrete (non-wildcard) bind host is trusted too — a
# rebinding attack sends the attacker's domain as Host, never the target IP. See
# jobfinder/security.py.
app.add_middleware(
    LocalSecurityMiddleware,
    allowed_hosts=build_allowed_hosts([*settings.allowed_hosts, settings.host]),
)

_STATIC = Path(__file__).parent / "static"
_MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MB — a CV is tiny; reject anything larger
_MAX_JOBS_PER_BATCH = 20

# The single persistence seam. Backend chosen by settings (sqlite default, memory in tests).
store = get_store(settings)


def _store_profile(profile: CVProfile) -> str:
    cv_id = secrets.token_urlsafe(9)
    store.save_profile(cv_id, profile)
    return cv_id


def _profile_summary(profile: CVProfile) -> dict:
    return {
        "name": profile.name,
        "skills": profile.skills,
        "titles": profile.titles,
        "years_experience": profile.years_experience,
        "seniority": profile.seniority,
        "location": profile.location,
        "suggested_keywords": profile.suggested_keywords,
        "text_chars": len(profile.raw_text),
    }


def _example_summary(ex: dict) -> dict:
    return {"id": ex["id"], "name": ex["name"], "chars": ex["chars"],
            "preview": (ex.get("text") or "")[:160].replace("\n", " ").strip()}


def _app_payload(a) -> dict:
    """An application dict enriched with freshly-computed letter guardrails, so the UI
    can flag placeholders / unsupported skill claims (verified, not just promised). The
    job's gap skills come from its stored snapshot — no profile lookup needed."""
    d = a.to_dict()
    job = d.get("job") if isinstance(d.get("job"), dict) else {}
    d["guardrails"] = check_letter(d.get("body") or "", (job or {}).get("missing_skills"))
    return d


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class SearchRequest(BaseModel):
    cv_id: str
    keywords: str = ""
    location: str = ""
    sources: list[str] = []          # empty → server uses the configured default sources
    limit_per_source: int = 25
    remote: bool = False
    days: int | None = None
    semantic: bool = False
    min_score: float = 0.0


class SaveSearchRequest(BaseModel):
    name: str = "Saved search"
    cv_id: str = ""
    keywords: str = ""
    location: str = ""
    sources: list[str] = []
    limit_per_source: int = 25
    remote: bool = False
    days: int | None = None
    semantic: bool = False
    min_score: float = 0.0


class SaveApplicationRequest(BaseModel):
    cv_id: str = ""
    job: dict


class GenerateRequest(BaseModel):
    cv_id: str
    jobs: list[dict] = []
    tone: str = "professional"
    length: str = "standard"
    use_llm: bool = True
    redact_pii: bool = False


class RegenerateRequest(BaseModel):
    cv_id: str = ""
    tone: str = "professional"
    length: str = "standard"
    use_llm: bool = True
    redact_pii: bool = False


class TailorRequest(BaseModel):
    cv_id: str = ""
    use_llm: bool = True
    redact_pii: bool = False


class ApplicationUpdate(BaseModel):
    status: str | None = None
    notes: str | None = None
    subject: str | None = None
    body: str | None = None


class ProfileUpdate(BaseModel):
    """User corrections to the parsed CV profile. Only provided fields are changed."""
    name: str | None = None
    titles: list[str] | None = None
    skills: list[str] | None = None
    location: str | None = None
    seniority: str | None = None
    years_experience: int | None = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return (_STATIC / "index.html").read_text(encoding="utf-8")


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "version": __version__, "storage": settings.storage}


@app.get("/api/sources")
def sources() -> dict:
    return {
        "sources": available_sources(),
        "default_sources": settings.default_sources,
        "jsearch_key_present": settings.jsearch_key_present,   # kept for compatibility
        "keyed": settings.keyed_present,                       # {source: key_present}
    }


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)) -> JSONResponse:
    # Reject oversized uploads before pulling the whole thing into memory.
    if file.size is not None and file.size > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 25 MB).")
    data = await file.read()
    if len(data) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 25 MB).")
    if not data:
        raise HTTPException(status_code=400, detail="Empty file.")
    try:
        text = extract_text_from_bytes(data, file.filename or "cv.txt")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    profile = build_profile(text)
    cv_id = _store_profile(profile)
    warning = None
    if looks_empty(text):
        warning = ("This file produced almost no text — it may be a scanned/image-only "
                   "PDF. Try a text-based PDF/DOCX, or paste your CV text instead.")
    return JSONResponse({"cv_id": cv_id, "profile": _profile_summary(profile), "warning": warning})


@app.post("/api/upload-text")
async def upload_text(text: str = Form(...)) -> JSONResponse:
    if not text or not text.strip():
        raise HTTPException(status_code=400, detail="No text provided.")
    profile = build_profile(text)
    cv_id = _store_profile(profile)
    return JSONResponse({"cv_id": cv_id, "profile": _profile_summary(profile), "warning": None})


def _clean_list(values: list[str] | None, *, lower: bool = False, cap: int = 100) -> list[str]:
    """Strip/dedupe a user-supplied list, dropping blanks. Order-preserving, bounded."""
    out: list[str] = []
    seen: set[str] = set()
    for v in values or []:
        v = (str(v) if v is not None else "").strip()
        if lower:
            v = v.lower()
        if v and v not in seen:
            seen.add(v)
            out.append(v)
        if len(out) >= cap:
            break
    return out


@app.patch("/api/profile/{cv_id}")
async def update_profile(cv_id: str, req: ProfileUpdate) -> JSONResponse:
    """Apply the user's corrections to a parsed profile — the whole funnel's accuracy
    rests on cv_parser heuristics, so letting the user fix them lifts every later step."""
    profile = store.get_profile(cv_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="CV not found — upload it again.")

    # Only fields the client actually sent are touched (None = leave unchanged).
    if req.skills is not None:
        profile.skills = _clean_list(req.skills, lower=True)
    if req.titles is not None:
        profile.titles = _clean_list(req.titles, cap=20)
    if req.name is not None:
        profile.name = req.name.strip() or None
    if req.location is not None:
        profile.location = req.location.strip() or None
    if req.seniority is not None:
        profile.seniority = (req.seniority.strip().lower() or None)
    if req.years_experience is not None:
        try:
            profile.years_experience = max(0, min(int(req.years_experience), 80))
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail="years_experience must be a number.")

    # A corrected title/skill must also drive the default search query, otherwise an
    # empty keyword box would still search for the parser's original wrong guess.
    if req.titles is not None or req.skills is not None:
        profile.suggested_keywords = default_query(profile.titles, profile.skills)

    store.save_profile(cv_id, profile)
    return JSONResponse({"cv_id": cv_id, "profile": _profile_summary(profile)})


def _build_settings(keywords, location, sources, limit_per_source, remote, days, semantic, min_score) -> SearchSettings:
    # Keep only known sources, de-duplicated and order-preserving — guards against a
    # client sending unknown or repeated names (which would amplify outbound requests).
    known = set(available_sources())
    chosen = list(dict.fromkeys(s for s in (sources or []) if s in known)) or list(settings.default_sources)
    return SearchSettings(
        keywords=keywords, location=location, sources=chosen,
        limit_per_source=max(1, min(limit_per_source, 50)),
        remote=remote, days=days, semantic=semantic, min_score=min_score,
    )


@app.post("/api/search")
def search(req: SearchRequest) -> JSONResponse:
    profile = store.get_profile(req.cv_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="CV not found — please upload your CV again.")

    search_settings = _build_settings(req.keywords, req.location, req.sources, req.limit_per_source,
                                      req.remote, req.days, req.semantic, req.min_score)
    result = find_jobs(profile, search_settings)
    return JSONResponse({
        "jobs": [j.to_dict() for j in result.jobs],
        "warnings": result.warnings,
        "counts": result.counts,
        "query": search_settings.keywords or profile.suggested_keywords,
    })


# ---------------------------------------------------------------------------
# Generation config + style examples
# ---------------------------------------------------------------------------

@app.get("/api/draft-config")
def draft_config() -> dict:
    return {
        "llm_available": llm_available(),
        "model": settings.model,
        "statuses": STATUSES,
        "suggested_next": SUGGESTED_NEXT,
        # Disclose the one egress so the UI can show it: with a key, the Claude path sends
        # the candidate's CV text + the job description to Anthropic. Offer redaction.
        "llm_egress": {
            "provider": "Anthropic",
            "sends": "your CV text, any style examples you've uploaded, and the job description",
            "redact_default": settings.redact_pii_default,
        },
    }


@app.post("/api/examples")
async def add_example(file: UploadFile = File(...)) -> JSONResponse:
    if file.size is not None and file.size > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 25 MB).")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file.")
    if len(data) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 25 MB).")
    try:
        text = extract_text_from_bytes(data, file.filename or "example.txt")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _store_example(file.filename or "example", text)


@app.post("/api/examples-text")
async def add_example_text(text: str = Form(...), name: str = Form("Pasted example")) -> JSONResponse:
    if not text or not text.strip():
        raise HTTPException(status_code=400, detail="No text provided.")
    return _store_example(name, text)


def _store_example(name: str, text: str) -> JSONResponse:
    ex = {"id": secrets.token_urlsafe(6), "name": name, "text": text, "chars": len(text)}
    store.save_example(ex)
    return JSONResponse(_example_summary(ex))


@app.get("/api/examples")
def list_examples() -> dict:
    return {"examples": [_example_summary(e) for e in store.list_examples()]}


@app.delete("/api/examples/{eid}")
def delete_example(eid: str) -> dict:
    store.delete_example(eid)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Applications (the pipeline / tracker)
# ---------------------------------------------------------------------------

@app.post("/api/applications")
def save_application(req: SaveApplicationRequest) -> JSONResponse:
    """Save a job to the pipeline as a 'saved' application (no letter yet)."""
    if not req.job or not req.job.get("title"):
        raise HTTPException(status_code=400, detail="Missing job.")
    appn = new_application(req.job, cv_id=req.cv_id, status="saved")
    store.save_application(appn)
    return JSONResponse(_app_payload(appn))


@app.post("/api/applications/generate")
def generate_applications(req: GenerateRequest) -> JSONResponse:
    """Create applications for the selected jobs and generate a cover letter for each."""
    profile = store.get_profile(req.cv_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="CV not found — please upload your CV again.")
    if not req.jobs:
        raise HTTPException(status_code=400, detail="No roles selected.")

    options = DraftOptions(tone=req.tone, length=req.length, use_llm=req.use_llm, redact_pii=req.redact_pii)
    examples = [e["text"] for e in store.list_examples()]
    created = []
    for job in req.jobs[:_MAX_JOBS_PER_BATCH]:
        appn = new_application(job, cv_id=req.cv_id)
        draft = generate_draft(profile, job, options, examples=examples)
        attach_letter(appn, draft.subject, draft.body, draft.generator, draft.note)
        store.save_application(appn)
        created.append(_app_payload(appn))
    return JSONResponse({"applications": created, "used_llm": options.use_llm and llm_available()})


@app.get("/api/applications")
def list_applications() -> dict:
    return {"applications": [_app_payload(a) for a in store.list_applications()], "statuses": STATUSES}


@app.get("/api/applications/{aid}")
def get_application(aid: str) -> JSONResponse:
    a = store.get_application(aid)
    if a is None:
        raise HTTPException(status_code=404, detail="Application not found.")
    return JSONResponse(_app_payload(a))


@app.patch("/api/applications/{aid}")
def update_application(aid: str, upd: ApplicationUpdate) -> JSONResponse:
    a = store.get_application(aid)
    if a is None:
        raise HTTPException(status_code=404, detail="Application not found.")
    if upd.status is not None:
        try:
            set_status(a, upd.status)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    if upd.notes is not None:
        a.notes = upd.notes
        a.updated = time.time()
    if upd.subject is not None:
        a.subject = upd.subject
        a.updated = time.time()
    if upd.body is not None:
        a.body = upd.body
        a.updated = time.time()
    store.save_application(a)
    return JSONResponse(_app_payload(a))


@app.post("/api/applications/{aid}/regenerate")
def regenerate_application(aid: str, req: RegenerateRequest) -> JSONResponse:
    a = store.get_application(aid)
    if a is None:
        raise HTTPException(status_code=404, detail="Application not found.")
    cv_id = req.cv_id or a.cv_id
    profile = store.get_profile(cv_id) if cv_id else None
    if profile is None:
        raise HTTPException(status_code=400,
                            detail="The CV for this application isn't available — re-upload your CV.")
    options = DraftOptions(tone=req.tone, length=req.length, use_llm=req.use_llm, redact_pii=req.redact_pii)
    examples = [e["text"] for e in store.list_examples()]
    draft = generate_draft(profile, job_snapshot(a), options, examples=examples)
    attach_letter(a, draft.subject, draft.body, draft.generator, draft.note)
    a.cv_id = cv_id
    store.save_application(a)
    return JSONResponse(_app_payload(a))


@app.post("/api/applications/{aid}/tailor")
def tailor_application(aid: str, req: TailorRequest) -> JSONResponse:
    a = store.get_application(aid)
    if a is None:
        raise HTTPException(status_code=404, detail="Application not found.")
    cv_id = req.cv_id or a.cv_id
    profile = store.get_profile(cv_id) if cv_id else None
    if profile is None:
        raise HTTPException(status_code=400,
                            detail="The CV for this application isn't available — re-upload your CV.")
    return JSONResponse(generate_tailoring(profile, job_snapshot(a), use_llm=req.use_llm, redact_pii=req.redact_pii))


@app.delete("/api/applications/{aid}")
def delete_application(aid: str) -> dict:
    store.delete_application(aid)
    return {"ok": True}


@app.get("/api/applications/{aid}/export")
def export_application(aid: str) -> PlainTextResponse:
    a = store.get_application(aid)
    if a is None:
        raise HTTPException(status_code=404, detail="Application not found.")
    safe = "".join(c if c.isalnum() or c in " -_" else "" for c in f"{a.company}_{a.job_title}").strip()
    filename = (safe or "application")[:60].replace(" ", "_") + ".txt"
    content = f"Subject: {a.subject}\n\n{a.body}\n"
    return PlainTextResponse(content, headers={
        "Content-Disposition": f'attachment; filename="{filename}"'
    })


# ---------------------------------------------------------------------------
# Insights (pipeline analytics, derived from applications)
# ---------------------------------------------------------------------------

@app.get("/api/insights")
def insights() -> dict:
    return compute_insights(store.list_applications())


# ---------------------------------------------------------------------------
# Saved searches (resurface what's new since last check)
# ---------------------------------------------------------------------------

@app.post("/api/saved-searches")
def create_saved_search(req: SaveSearchRequest) -> JSONResponse:
    s = new_saved_search(req.name, req.model_dump())
    store.save_saved_search(s)
    return JSONResponse(s.summary())


@app.get("/api/saved-searches")
def list_saved_searches() -> dict:
    return {"searches": [s.summary() for s in store.list_saved_searches()]}


@app.delete("/api/saved-searches/{sid}")
def delete_saved_search(sid: str) -> dict:
    store.delete_saved_search(sid)
    return {"ok": True}


@app.post("/api/saved-searches/{sid}/seen")
def mark_saved_search_seen(sid: str) -> dict:
    s = store.get_saved_search(sid)
    if s is None:
        raise HTTPException(status_code=404, detail="Saved search not found.")
    mark_seen(s)
    store.save_saved_search(s)
    return {"ok": True, "new_count": 0}


def _run_one(s) -> dict:
    """Run a saved search; update its seen-set/new_count; return the ranked jobs + new ids."""
    profile = store.get_profile(s.cv_id) if s.cv_id else None
    if profile is None:
        raise HTTPException(status_code=400,
                            detail="The CV for this saved search isn't available — re-upload your CV.")
    settings_ = _build_settings(s.keywords, s.location, s.sources, s.limit_per_source,
                                s.remote, s.days, s.semantic, s.min_score)
    result = find_jobs(profile, settings_)
    new_ids = register_run(s, [j.id for j in result.jobs])
    store.save_saved_search(s)
    return {
        "jobs": [j.to_dict() for j in result.jobs],
        "new_ids": new_ids,
        "new_count": s.new_count,
        "warnings": result.warnings,
        "counts": result.counts,
        "query": settings_.keywords or "",
        "name": s.name,
    }


@app.post("/api/saved-searches/{sid}/run")
def run_saved_search(sid: str) -> JSONResponse:
    s = store.get_saved_search(sid)
    if s is None:
        raise HTTPException(status_code=404, detail="Saved search not found.")
    return JSONResponse(_run_one(s))


@app.post("/api/saved-searches/run-all")
def run_all_saved_searches() -> dict:
    out = []
    for s in store.list_saved_searches():
        try:
            r = _run_one(s)
            out.append({"id": s.id, "name": s.name, "new_count": r["new_count"]})
        except HTTPException as e:
            out.append({"id": s.id, "name": s.name, "new_count": s.new_count, "error": e.detail})
        except Exception as e:
            out.append({"id": s.id, "name": s.name, "new_count": s.new_count, "error": str(e)})
    return {"searches": out}


# Static assets (css/js)
app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")
