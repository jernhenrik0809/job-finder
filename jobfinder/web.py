"""FastAPI backend serving the Job Finder UI and JSON API."""
from __future__ import annotations

import secrets
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .cv_parser import CVProfile, build_profile, extract_text_from_bytes, looks_empty
from .drafts import ApplicationDraft, DraftOptions, generate_draft, llm_available, DEFAULT_MODEL
from .engine import SearchSettings, find_jobs
from .sources import available_sources

app = FastAPI(title="Job Finder", version="1.0.0")

_STATIC = Path(__file__).parent / "static"

# Simple in-memory store of parsed CVs for the lifetime of the process.
# Keyed by a random id handed back to the browser. Fine for a local single-user app.
_PROFILES: dict[str, CVProfile] = {}
_MAX_PROFILES = 50
_MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MB — a CV is tiny; reject anything larger


def _store_profile(profile: CVProfile) -> str:
    if len(_PROFILES) > _MAX_PROFILES:
        # drop an arbitrary old entry to bound memory
        _PROFILES.pop(next(iter(_PROFILES)))
    cv_id = secrets.token_urlsafe(9)
    _PROFILES[cv_id] = profile
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


# Application-draft outbox + uploaded style examples (single-user, in-memory).
_EXAMPLES: dict[str, dict] = {}     # id -> {id, name, text, chars}
_DRAFTS: dict[str, ApplicationDraft] = {}
_MAX_EXAMPLES = 10
_MAX_DRAFTS = 100
_MAX_JOBS_PER_BATCH = 20


def _example_summary(ex: dict) -> dict:
    return {"id": ex["id"], "name": ex["name"], "chars": ex["chars"],
            "preview": ex["text"][:160].replace("\n", " ").strip()}


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class SearchRequest(BaseModel):
    cv_id: str
    keywords: str = ""
    location: str = ""
    sources: list[str] = ["remotive"]
    limit_per_source: int = 25
    remote: bool = False
    days: int | None = None
    semantic: bool = False
    min_score: float = 0.0


class GenerateRequest(BaseModel):
    cv_id: str
    jobs: list[dict] = []
    tone: str = "professional"
    length: str = "standard"
    use_llm: bool = True


class DraftUpdate(BaseModel):
    subject: str | None = None
    body: str | None = None
    status: str | None = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return (_STATIC / "index.html").read_text(encoding="utf-8")


@app.get("/api/sources")
def sources() -> dict:
    import os
    return {
        "sources": available_sources(),
        "jsearch_key_present": bool(os.environ.get("RAPIDAPI_KEY") or os.environ.get("JSEARCH_API_KEY")),
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


@app.post("/api/search")
def search(req: SearchRequest) -> JSONResponse:
    profile = _PROFILES.get(req.cv_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="CV not found — please upload your CV again.")

    # Keep only known sources, de-duplicated and order-preserving — guards against a
    # client sending unknown or repeated names (which would amplify outbound requests).
    known = set(available_sources())
    chosen = list(dict.fromkeys(s for s in req.sources if s in known)) or ["remotive"]

    settings = SearchSettings(
        keywords=req.keywords,
        location=req.location,
        sources=chosen,
        limit_per_source=max(1, min(req.limit_per_source, 50)),
        remote=req.remote,
        days=req.days,
        semantic=req.semantic,
        min_score=req.min_score,
    )
    result = find_jobs(profile, settings)
    return JSONResponse({
        "jobs": [j.to_dict() for j in result.jobs],
        "warnings": result.warnings,
        "counts": result.counts,
        "query": settings.keywords or profile.suggested_keywords,
    })


# ---------------------------------------------------------------------------
# Application drafts (the "auto-apply" outbox) + style examples
# ---------------------------------------------------------------------------

@app.get("/api/draft-config")
def draft_config() -> dict:
    return {"llm_available": llm_available(), "model": DEFAULT_MODEL}


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
    if len(_EXAMPLES) >= _MAX_EXAMPLES:
        _EXAMPLES.pop(next(iter(_EXAMPLES)))
    eid = secrets.token_urlsafe(6)
    ex = {"id": eid, "name": name, "text": text, "chars": len(text)}
    _EXAMPLES[eid] = ex
    return JSONResponse(_example_summary(ex))


@app.get("/api/examples")
def list_examples() -> dict:
    return {"examples": [_example_summary(e) for e in _EXAMPLES.values()]}


@app.delete("/api/examples/{eid}")
def delete_example(eid: str) -> dict:
    _EXAMPLES.pop(eid, None)
    return {"ok": True}


@app.post("/api/drafts/generate")
def generate_drafts(req: GenerateRequest) -> JSONResponse:
    profile = _PROFILES.get(req.cv_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="CV not found — please upload your CV again.")
    if not req.jobs:
        raise HTTPException(status_code=400, detail="No roles selected.")

    options = DraftOptions(tone=req.tone, length=req.length, use_llm=req.use_llm)
    examples = [e["text"] for e in _EXAMPLES.values()]
    created = []
    for job in req.jobs[:_MAX_JOBS_PER_BATCH]:
        draft = generate_draft(profile, job, options, examples=examples)
        if len(_DRAFTS) >= _MAX_DRAFTS:
            _DRAFTS.pop(next(iter(_DRAFTS)))
        _DRAFTS[draft.id] = draft
        created.append(draft.to_dict())
    return JSONResponse({"drafts": created, "used_llm": options.use_llm and llm_available()})


@app.get("/api/drafts")
def list_drafts() -> dict:
    return {"drafts": [d.to_dict() for d in _DRAFTS.values()]}


@app.put("/api/drafts/{did}")
def update_draft(did: str, upd: DraftUpdate) -> JSONResponse:
    draft = _DRAFTS.get(did)
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft not found.")
    if upd.subject is not None:
        draft.subject = upd.subject
    if upd.body is not None:
        draft.body = upd.body
    if upd.status is not None and upd.status in ("draft", "ready"):
        draft.status = upd.status
    return JSONResponse(draft.to_dict())


@app.delete("/api/drafts/{did}")
def delete_draft(did: str) -> dict:
    _DRAFTS.pop(did, None)
    return {"ok": True}


@app.get("/api/drafts/{did}/export")
def export_draft(did: str) -> PlainTextResponse:
    draft = _DRAFTS.get(did)
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft not found.")
    safe = "".join(c if c.isalnum() or c in " -_" else "" for c in f"{draft.company}_{draft.job_title}").strip()
    filename = (safe or "application")[:60].replace(" ", "_") + ".txt"
    content = f"Subject: {draft.subject}\n\n{draft.body}\n"
    return PlainTextResponse(content, headers={
        "Content-Disposition": f'attachment; filename="{filename}"'
    })


# Static assets (css/js)
app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")
