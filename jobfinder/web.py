"""FastAPI backend serving the Job Finder UI and JSON API.

State lives in a Store (memory or SQLite) behind the repository interface — not in
module-global dicts — so the Outbox and parsed CVs survive a restart when the SQLite
backend is active (the default).
"""
from __future__ import annotations

import secrets
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import __version__
from .config import settings
from .cv_parser import CVProfile, build_profile, extract_text_from_bytes, looks_empty
from .drafts import DraftOptions, generate_draft, llm_available
from .engine import SearchSettings, find_jobs
from .sources import available_sources
from .store import get_store

app = FastAPI(title="Job Finder", version=__version__)

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


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "version": __version__, "storage": settings.storage}


@app.get("/api/sources")
def sources() -> dict:
    return {
        "sources": available_sources(),
        "default_sources": settings.default_sources,
        "jsearch_key_present": settings.jsearch_key_present,
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
    profile = store.get_profile(req.cv_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="CV not found — please upload your CV again.")

    # Keep only known sources, de-duplicated and order-preserving — guards against a
    # client sending unknown or repeated names (which would amplify outbound requests).
    known = set(available_sources())
    chosen = list(dict.fromkeys(s for s in req.sources if s in known)) or list(settings.default_sources)

    search_settings = SearchSettings(
        keywords=req.keywords,
        location=req.location,
        sources=chosen,
        limit_per_source=max(1, min(req.limit_per_source, 50)),
        remote=req.remote,
        days=req.days,
        semantic=req.semantic,
        min_score=req.min_score,
    )
    result = find_jobs(profile, search_settings)
    return JSONResponse({
        "jobs": [j.to_dict() for j in result.jobs],
        "warnings": result.warnings,
        "counts": result.counts,
        "query": search_settings.keywords or profile.suggested_keywords,
    })


# ---------------------------------------------------------------------------
# Application drafts (the "auto-apply" outbox) + style examples
# ---------------------------------------------------------------------------

@app.get("/api/draft-config")
def draft_config() -> dict:
    return {"llm_available": llm_available(), "model": settings.model}


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


@app.post("/api/drafts/generate")
def generate_drafts(req: GenerateRequest) -> JSONResponse:
    profile = store.get_profile(req.cv_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="CV not found — please upload your CV again.")
    if not req.jobs:
        raise HTTPException(status_code=400, detail="No roles selected.")

    options = DraftOptions(tone=req.tone, length=req.length, use_llm=req.use_llm)
    examples = [e["text"] for e in store.list_examples()]
    created = []
    for job in req.jobs[:_MAX_JOBS_PER_BATCH]:
        draft = generate_draft(profile, job, options, examples=examples)
        store.save_draft(draft)
        created.append(draft.to_dict())
    return JSONResponse({"drafts": created, "used_llm": options.use_llm and llm_available()})


@app.get("/api/drafts")
def list_drafts() -> dict:
    return {"drafts": [d.to_dict() for d in store.list_drafts()]}


@app.put("/api/drafts/{did}")
def update_draft(did: str, upd: DraftUpdate) -> JSONResponse:
    draft = store.get_draft(did)
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft not found.")
    if upd.subject is not None:
        draft.subject = upd.subject
    if upd.body is not None:
        draft.body = upd.body
    if upd.status is not None and upd.status in ("draft", "ready"):
        draft.status = upd.status
    store.save_draft(draft)            # persist the edit (backend-agnostic)
    return JSONResponse(draft.to_dict())


@app.delete("/api/drafts/{did}")
def delete_draft(did: str) -> dict:
    store.delete_draft(did)
    return {"ok": True}


@app.get("/api/drafts/{did}/export")
def export_draft(did: str) -> PlainTextResponse:
    draft = store.get_draft(did)
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
