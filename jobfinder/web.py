"""FastAPI backend serving the Job Finder UI and JSON API.

State lives in a Store (memory or SQLite) behind the repository interface — not in
module-global dicts — so the pipeline and parsed CVs survive a restart when the SQLite
backend is active (the default). The durable unit is the Application (a tracked job in
your pipeline); a generated cover letter is its current artifact.
"""
from __future__ import annotations

import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import __version__
from . import alerts
from .applications import (
    STATUSES, SUGGESTED_NEXT, attach_letter, job_snapshot, new_application, set_status,
)
from .bench import Project, rank_bench_for_project
from .case_studies import DISCLOSURE, CaseStudy, new_case_study
from .clients import Client, new_client
from .config import settings
from .consultants import (
    DATA_ORIGINS, ENGAGEMENT_TYPES, STATUSES as CONSULTANT_STATUSES,
    Consultant, consultant_from_profile, new_consultant,
)
from .house import House
from .cv_parser import CVProfile, build_profile, default_query, extract_text_from_bytes, looks_empty
from .drafts import DraftOptions, generate_draft, llm_available
from .engine import SearchSettings, find_jobs
from .guardrails import check_letter, check_proposal, has_blocking
from .opportunities import (
    STATUSES as OPP_STATUSES, SUGGESTED_NEXT as OPP_SUGGESTED_NEXT,
    attach_proposal, margin_of, new_opportunity, record_event, record_export, set_staffing,
    set_status as set_opp_status,
)
from .proposals import ProposalOptions, generate_proposal
from .insights import compute_insights
from .saved_searches import new_saved_search, register_run, mark_seen
from .security import LocalSecurityMiddleware, build_allowed_hosts
from .sources import available_sources
from . import secrets_store
from .store import get_store
from .tailor import generate_tailoring

@asynccontextmanager
async def _lifespan(_app):
    # Start the opt-in alerts loop on boot (it idles while disabled); stop it on shutdown.
    alert_scheduler.start()
    try:
        yield
    finally:
        alert_scheduler.stop()


app = FastAPI(title="Job Finder", version=__version__, lifespan=_lifespan)

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

# Opt-in background alerts (off by default). The daemon thread idles while disabled and
# only re-runs saved searches / raises reminders once the user turns it on (Settings).
alert_scheduler = alerts.AlertScheduler(store, find_jobs)


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
    gigs_only: bool = False          # "consulting/contract only"


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
    gigs_only: bool = False


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


class SettingsUpdate(BaseModel):
    """Credentials + model tier set from the Settings page. None = leave unchanged,
    "" = clear. Keys are written to a local owner-only file, never the DB, never returned."""
    anthropic_key: str | None = None
    rapidapi_key: str | None = None
    adzuna_app_id: str | None = None
    adzuna_app_key: str | None = None
    jooble_key: str | None = None
    careerjet_affid: str | None = None
    freelancer_token: str | None = None
    findwork_token: str | None = None
    model: str | None = None


class ProfileUpdate(BaseModel):
    """User corrections to the parsed CV profile. Only provided fields are changed."""
    name: str | None = None
    titles: list[str] | None = None
    skills: list[str] | None = None
    location: str | None = None
    seniority: str | None = None
    years_experience: int | None = None


class ConsultantCreate(BaseModel):
    """Onboard a bench member. Provide ``text`` (a CV to parse) OR ``cv_id`` (an already-
    uploaded profile) to seed skills/raw_text, plus any explicit field overrides; or just a
    ``name`` for a stub to fill in later."""
    name: str | None = None
    text: str | None = None
    cv_id: str | None = None
    title: str | None = None
    skills: list[str] | None = None
    seniority: str | None = None
    languages: list[str] | None = None
    available_from: str | None = None
    available_until: str | None = None
    hours_per_week: int | None = None
    cost_rate: float | None = None
    sell_rate: float | None = None
    currency: str | None = None
    engagement_type: str | None = None
    right_to_present: bool | None = None
    data_origin: str | None = None
    source_detail: str | None = None
    consent_note: str | None = None
    clearance: str | None = None
    certifications: list[str] | None = None
    location: str | None = None
    remote_ok: bool | None = None
    notes: str | None = None


class ConsultantUpdate(BaseModel):
    """Edit a bench member. Only provided (non-None) fields are changed."""
    name: str | None = None
    title: str | None = None
    skills: list[str] | None = None
    seniority: str | None = None
    languages: list[str] | None = None
    available_from: str | None = None
    available_until: str | None = None
    hours_per_week: int | None = None
    cost_rate: float | None = None
    sell_rate: float | None = None
    currency: str | None = None
    engagement_type: str | None = None
    right_to_present: bool | None = None
    data_origin: str | None = None
    source_detail: str | None = None
    consent_note: str | None = None
    clearance: str | None = None
    certifications: list[str] | None = None
    location: str | None = None
    remote_ok: bool | None = None
    status: str | None = None
    notes: str | None = None
    raw_text: str | None = None


class HouseUpdate(BaseModel):
    """Edit the single-row house identity. Only provided fields are changed."""
    name: str | None = None
    tagline: str | None = None
    voice: str | None = None
    signatory: str | None = None
    boilerplate: str | None = None
    contact: str | None = None
    website: str | None = None


class BenchRankRequest(BaseModel):
    """Rank the bench against a project. Supply the fields directly, paste a brief as ``text``
    (parsed for skills when ``skills`` is empty), or pass a search-result ``job`` card. String
    fields accept null (the UI sends null for empty inputs); the handler coerces null → ""."""
    title: str | None = None
    description: str | None = None
    text: str | None = None
    skills: list[str] | None = None
    location: str | None = None
    remote: bool = False
    rate_ceiling: float | None = None
    currency: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    required_clearance: str | None = None
    job: dict | None = None


class ProposalGenerateRequest(BaseModel):
    """Generate a house proposal for a project (same project fields as BenchRankRequest) putting
    forward the chosen ``consultant_ids``."""
    title: str | None = None
    description: str | None = None
    text: str | None = None
    skills: list[str] | None = None
    location: str | None = None
    remote: bool = False
    rate_ceiling: float | None = None
    currency: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    required_clearance: str | None = None
    job: dict | None = None
    consultant_ids: list[str] = []
    tone: str = "professional"
    length: str = "standard"
    use_llm: bool = True
    redact_pii: bool | None = None          # None → fall back to the server's privacy default


class ProposalExportRequest(BaseModel):
    """Export a (possibly human-edited) proposal as text — re-runs the QA gate and refuses
    (409) if a blocking finding remains, so an edited fabrication can't slip out."""
    subject: str | None = None
    body: str = ""
    project_title: str | None = None
    consultant_ids: list[str] = []


class OpportunityCreate(BaseModel):
    """Start pursuing a project (a posting or a warm lead). Same project fields as the rank/
    proposal requests; idempotent on (source, source_uid) for ingested postings."""
    title: str | None = None
    description: str | None = None
    text: str | None = None
    skills: list[str] | None = None
    location: str | None = None
    remote: bool = False
    rate_ceiling: float | None = None
    currency: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    required_clearance: str | None = None
    job: dict | None = None
    kind: str = "posting"                  # posting | warm
    consultant_ids: list[str] = []         # optional initial staffing


class OpportunityUpdate(BaseModel):
    """Edit a pursued opportunity. Only provided fields change; ``status`` is validated."""
    status: str | None = None
    notes: str | None = None
    staffed: list[dict] | None = None      # replace the per-consultant bid lines
    rate_ceiling: float | None = None
    currency: str | None = None
    start_date: str | None = None
    client_id: str | None = None           # link this opportunity to a client/account


class ClientCreate(BaseModel):
    """Create a client/account (the direct-warm relationship layer)."""
    name: str = ""
    sector: str = ""
    contacts: list[dict] | None = None     # [{name, role, email, phone}]
    do_not_bid: bool = False
    past_projects: list[str] | None = None
    notes: str = ""


class ClientUpdate(BaseModel):
    """Edit a client. Only provided fields change."""
    name: str | None = None
    sector: str | None = None
    contacts: list[dict] | None = None
    do_not_bid: bool | None = None
    past_projects: list[str] | None = None
    notes: str | None = None


class CaseStudyCreate(BaseModel):
    """Create a grounded proof record (a delivered engagement)."""
    title: str = ""
    client_name: str = ""
    client_anonymized: str = ""
    sector: str = ""
    summary: str = ""
    outcomes: list[dict] | None = None     # [{metric, value, unit}]
    skills: list[str] | None = None
    consultant_ids: list[str] | None = None
    disclosure: str = "confidential"       # public | anonymized_only | confidential
    reference_contact: str = ""
    reference_consent: bool = False
    start_date: str = ""
    end_date: str = ""
    notes: str = ""


class CaseStudyUpdate(BaseModel):
    """Edit a case study. Only provided fields change."""
    title: str | None = None
    client_name: str | None = None
    client_anonymized: str | None = None
    sector: str | None = None
    summary: str | None = None
    outcomes: list[dict] | None = None
    skills: list[str] | None = None
    consultant_ids: list[str] | None = None
    disclosure: str | None = None
    reference_contact: str | None = None
    reference_consent: bool | None = None
    start_date: str | None = None
    end_date: str | None = None
    notes: str | None = None


class OpportunityProposalRequest(BaseModel):
    """Generate a proposal INTO an opportunity. Uses the given consultants, or the opportunity's
    staffed consultants when omitted; persists the artifact + QA + an audit event."""
    consultant_ids: list[str] | None = None
    tone: str = "professional"
    length: str = "standard"
    use_llm: bool = True
    redact_pii: bool | None = None
    override_do_not_bid: bool = False      # bid anyway for a do-not-bid client (audited)


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
        "jsearch_key_present": secrets_store.present()["jsearch"],   # kept for compatibility
        "keyed": secrets_store.present(),                      # {source: key_present}
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


def _build_settings(keywords, location, sources, limit_per_source, remote, days, semantic,
                    min_score, gigs_only=False) -> SearchSettings:
    # Keep only known sources, de-duplicated and order-preserving — guards against a
    # client sending unknown or repeated names (which would amplify outbound requests).
    known = set(available_sources())
    chosen = list(dict.fromkeys(s for s in (sources or []) if s in known)) or list(settings.default_sources)
    return SearchSettings(
        keywords=keywords, location=location, sources=chosen,
        limit_per_source=max(1, min(limit_per_source, 50)),
        remote=remote, days=days, semantic=semantic, min_score=min_score, gigs_only=gigs_only,
    )


@app.post("/api/search")
def search(req: SearchRequest) -> JSONResponse:
    profile = store.get_profile(req.cv_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="CV not found — please upload your CV again.")

    search_settings = _build_settings(req.keywords, req.location, req.sources, req.limit_per_source,
                                      req.remote, req.days, req.semantic, req.min_score, req.gigs_only)
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
        "model": secrets_store.model(),
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


# Selectable Claude model tiers (with a rough relative cost, for the Settings cost hint).
_MODEL_TIERS = [
    {"id": "claude-opus-4-8", "label": "Opus 4.8 — best quality", "cost": "$$$", "per_letter": "~$0.06"},
    {"id": "claude-sonnet-4-6", "label": "Sonnet 4.6 — balanced", "cost": "$$", "per_letter": "~$0.015"},
    {"id": "claude-haiku-4-5", "label": "Haiku 4.5 — fastest / cheapest", "cost": "$", "per_letter": "~$0.004"},
]
_MODEL_IDS = {m["id"] for m in _MODEL_TIERS}
# logical secret -> the env var name shown to the user as the override that "locks" it
_KEY_ENV = {"anthropic_key": "ANTHROPIC_API_KEY", "rapidapi_key": "RAPIDAPI_KEY",
            "adzuna_app_id": "ADZUNA_APP_ID", "adzuna_app_key": "ADZUNA_APP_KEY",
            "jooble_key": "JOOBLE_API_KEY", "careerjet_affid": "CAREERJET_AFFID",
            "freelancer_token": "FREELANCER_TOKEN", "findwork_token": "FINDWORK_TOKEN",
            "model": "JOBFINDER_MODEL"}


def _settings_payload() -> dict:
    """Settings state — credential *presence* only (never the values), model + tiers, and
    which fields are locked by an environment variable."""
    get = secrets_store.get
    return {
        "present": {
            "anthropic": secrets_store.anthropic_present(),
            "rapidapi": bool(get("rapidapi_key")),
            "adzuna": bool(get("adzuna_app_id") and get("adzuna_app_key")),
            "jooble": bool(get("jooble_key")),
            "careerjet": bool(get("careerjet_affid")),
            "freelancer": bool(get("freelancer_token")),
            "findwork": bool(get("findwork_token")),
        },
        "env_locked": {name: secrets_store.is_env(name) for name in _KEY_ENV},
        "model": secrets_store.model(),
        "models": _MODEL_TIERS,
        "llm_available": llm_available(),
        "redact_pii_default": settings.redact_pii_default,
    }


@app.get("/api/settings")
def get_settings() -> dict:
    return _settings_payload()


@app.post("/api/settings")
def update_settings(req: SettingsUpdate) -> JSONResponse:
    values = {k: v for k, v in req.model_dump().items() if v is not None}
    if values.get("model") and values["model"] not in _MODEL_IDS:
        raise HTTPException(status_code=422, detail="Unknown model tier.")
    secrets_store.set_many(values)
    return JSONResponse(_settings_payload())


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
# Consulting engine — the bench (consultants), the house, and gig→bench matching
# ---------------------------------------------------------------------------

_CONSULTANT_ENUMS = {
    "engagement_type": (ENGAGEMENT_TYPES, "associate"),
    "data_origin": (DATA_ORIGINS, "direct_from_subject"),
    "status": (CONSULTANT_STATUSES, "active"),
}
_CONSULTANT_LIST_FIELDS = {"skills", "languages", "certifications"}
_CONSULTANT_STR_FIELDS = {
    "name", "title", "seniority", "available_from", "available_until", "currency",
    "source_detail", "consent_note", "clearance", "location", "notes", "raw_text",
}


def _apply_consultant_fields(c: Consultant, data: dict) -> None:
    """Apply provided (non-None) fields from a create/update payload onto a Consultant,
    coercing types and validating the small enum fields (unknown enum value → ignored)."""
    for k, v in data.items():
        if v is None or k in ("text", "cv_id"):
            continue
        if k in _CONSULTANT_LIST_FIELDS:
            setattr(c, k, _clean_list(v, lower=(k == "skills")))
        elif k in _CONSULTANT_ENUMS:
            allowed, _default = _CONSULTANT_ENUMS[k]
            vv = str(v).strip().lower()
            if vv in allowed:
                setattr(c, k, vv)
        elif k in _CONSULTANT_STR_FIELDS:
            setattr(c, k, str(v).strip())
        elif k == "hours_per_week":
            try:
                c.hours_per_week = max(0, min(int(v), 168))
            except (TypeError, ValueError):
                pass
        elif k in ("cost_rate", "sell_rate"):
            try:
                setattr(c, k, float(v))
            except (TypeError, ValueError):
                pass
        elif k in ("right_to_present", "remote_ok"):
            setattr(c, k, bool(v))
    c.updated = time.time()


@app.post("/api/consultants")
def create_consultant(req: ConsultantCreate) -> JSONResponse:
    """Add a bench member — seeded from pasted CV text, an existing cv_id, or just a name."""
    data = req.model_dump()
    if req.text and req.text.strip():
        profile = build_profile(req.text)
        cv_id = _store_profile(profile)
        c = consultant_from_profile(profile, cv_id=cv_id)
    elif req.cv_id:
        profile = store.get_profile(req.cv_id)
        if profile is None:
            raise HTTPException(status_code=404, detail="CV not found — upload it again.")
        c = consultant_from_profile(profile, cv_id=req.cv_id)
    else:
        c = new_consultant((req.name or "").strip() or "Unnamed consultant")
    _apply_consultant_fields(c, data)             # explicit overrides win over the parsed CV
    if not (c.name or "").strip():
        c.name = "Unnamed consultant"
    store.save_consultant(c)
    return JSONResponse(c.to_dict())


@app.get("/api/consultants")
def list_consultants() -> dict:
    return {
        "consultants": [c.to_dict() for c in store.list_consultants()],
        "engagement_types": list(ENGAGEMENT_TYPES),
        "data_origins": list(DATA_ORIGINS),
        "statuses": list(CONSULTANT_STATUSES),
    }


@app.get("/api/consultants/{cid}")
def get_consultant(cid: str) -> JSONResponse:
    c = store.get_consultant(cid)
    if c is None:
        raise HTTPException(status_code=404, detail="Consultant not found.")
    return JSONResponse(c.to_dict())


@app.patch("/api/consultants/{cid}")
def update_consultant(cid: str, upd: ConsultantUpdate) -> JSONResponse:
    c = store.get_consultant(cid)
    if c is None:
        raise HTTPException(status_code=404, detail="Consultant not found.")
    _apply_consultant_fields(c, upd.model_dump())
    if not (c.name or "").strip():                # a consultant must keep a non-empty name (as on create)
        c.name = "Unnamed consultant"
    store.save_consultant(c)
    return JSONResponse(c.to_dict())


@app.delete("/api/consultants/{cid}")
def delete_consultant(cid: str) -> dict:
    store.delete_consultant(cid)
    return {"ok": True}


@app.get("/api/house")
def get_house() -> JSONResponse:
    h = store.get_house() or House()
    return JSONResponse(h.to_dict())


@app.post("/api/house")
def update_house(upd: HouseUpdate) -> JSONResponse:
    h = store.get_house() or House()
    for k, v in upd.model_dump().items():
        if v is not None:
            setattr(h, k, str(v).strip())
    if not h.created:
        h.created = time.time()
    h.updated = time.time()
    store.save_house(h)
    return JSONResponse(h.to_dict())


def _bench_match_payload(m) -> dict:
    return {
        "consultant": m.consultant.to_dict(),
        "score": m.score,
        "eligible": m.eligible,
        "disqualifiers": m.disqualifiers,
        "matched_skills": m.matched_skills,
        "missing_skills": m.missing_skills,
        "reasons": m.reasons,
        "notes": m.notes,
    }


def _project_from_request(req) -> tuple[Project, bool]:
    """Build a bench ``Project`` from a request (rank or proposal). Accepts explicit fields, a
    pasted brief (``text``), or a search-result ``job`` card. Returns (project, has_input)."""
    job = req.job if isinstance(getattr(req, "job", None), dict) else None
    title = (req.title or (job or {}).get("title") or "").strip()
    description = (req.description or req.text or (job or {}).get("description") or "").strip()
    skills = _clean_list(req.skills, lower=True) if req.skills is not None else None
    if not skills and job and isinstance(job.get("job_skills"), list):
        skills = _clean_list(job.get("job_skills"), lower=True)
    project = Project(
        title=title or "Untitled project",
        description=description,
        skills=skills or [],
        location=(req.location or (job or {}).get("location") or "").strip(),
        remote=bool(req.remote or (job or {}).get("remote")),
        rate_ceiling=req.rate_ceiling,
        currency=(req.currency or "").strip(),
        start_date=(req.start_date or "").strip(),
        end_date=(req.end_date or "").strip(),
        required_clearance=(req.required_clearance or "").strip(),
        source=((job or {}).get("source") or "").strip(),
        url=((job or {}).get("url") or "").strip(),
    )
    return project, bool(title or description)


@app.post("/api/bench/rank")
def rank_bench(req: BenchRankRequest) -> JSONResponse:
    """Match the whole bench against one project (an ingested posting or a pasted brief) and
    return consultants ranked best-first, ineligible ones zeroed with explicit reasons."""
    project, has_input = _project_from_request(req)
    if not has_input:
        raise HTTPException(status_code=400, detail="Describe the project (a title, brief, or job).")
    # Load the bench once (short lock), then score OUTSIDE any store lock (bench.py is pure).
    consultants = store.list_consultants()
    ranked = rank_bench_for_project(project, consultants)
    return JSONResponse({
        "project": {"title": project.title, "skills": project.skills, "location": project.location,
                    "remote": project.remote, "source": project.source, "url": project.url},
        "matches": [_bench_match_payload(m) for m in ranked],
        "bench_size": len(consultants),
    })


def _load_consultants(ids: list[str]) -> list:
    """Load proposed consultants by id, preserving the caller's order, skipping any missing."""
    out = []
    for cid in ids or []:
        c = store.get_consultant(cid)
        if c is not None:
            out.append(c)
    return out


@app.post("/api/proposals/generate")
def generate_proposal_endpoint(req: ProposalGenerateRequest) -> JSONResponse:
    """Draft a house proposal for a project, putting forward the chosen consultants, then run the
    QA gate. Returns the draft + findings + a ``blocking`` flag (export is refused while blocking).
    Never sends anything — a human exports and submits."""
    project, has_input = _project_from_request(req)
    if not has_input:
        raise HTTPException(status_code=400, detail="Describe the project (a title, brief, or job).")
    consultants = _load_consultants(req.consultant_ids)
    if not consultants:
        raise HTTPException(status_code=400, detail="Select at least one consultant to put forward.")
    # Privacy: a proposal carries third-party (consultant) data — default redaction to the
    # server's privacy setting unless the caller is explicit.
    redact = settings.redact_pii_default if req.redact_pii is None else bool(req.redact_pii)
    options = ProposalOptions(tone=req.tone, length=req.length, use_llm=req.use_llm, redact_pii=redact)
    examples = [e["text"] for e in store.list_examples()]
    house = store.get_house() or House()
    draft = generate_proposal(house, project, consultants, options, examples=examples)
    findings = check_proposal(draft.body, consultants)
    return JSONResponse({
        "proposal": draft.to_dict(),
        "qa": findings,
        "blocking": has_blocking(findings),
        "used_llm": options.use_llm and llm_available(),
    })


@app.post("/api/proposals/export")
def export_proposal_endpoint(req: ProposalExportRequest) -> PlainTextResponse:
    """Export a (possibly human-edited) proposal as a text file. Re-runs the QA gate against the
    proposed consultants and REFUSES with 409 if a blocking finding remains — so an edited
    fabrication can't slip past the gate on the way out."""
    body = (req.body or "").strip()
    if not body:
        raise HTTPException(status_code=400, detail="Nothing to export.")
    consultants = _load_consultants(req.consultant_ids)
    findings = check_proposal(body, consultants)
    if has_blocking(findings):
        raise HTTPException(status_code=409, detail={
            "message": "This proposal didn't pass the fabrication check — fix the flagged items before export.",
            "findings": findings,
        })
    safe = "".join(c if c.isalnum() or c in " -_" else "" for c in (req.project_title or "proposal")).strip()
    filename = (safe or "proposal")[:60].replace(" ", "_") + ".txt"
    subject = (req.subject or "").strip()
    content = (f"Subject: {subject}\n\n{body}\n" if subject else f"{body}\n")
    return PlainTextResponse(content, headers={"Content-Disposition": f'attachment; filename="{filename}"'})


# ---------------------------------------------------------------------------
# Opportunities (pursued projects + the proposal audit trail)
# ---------------------------------------------------------------------------

def _staff_lines(consultant_ids: list[str]) -> list[dict]:
    """Build per-consultant bid lines from the bench records (default rates from each consultant)."""
    lines = []
    for c in _load_consultants(consultant_ids or []):
        lines.append({"consultant_id": c.id, "consultant_name": c.name,
                      "cost_rate": c.cost_rate, "sell_rate": c.sell_rate, "currency": c.currency})
    return lines


def _opp_payload(opp) -> dict:
    d = opp.to_dict()
    d["blocking"] = has_blocking(opp.qa)          # is the stored proposal currently export-blocked?
    # Commercials: per-line margin + a total when every staffed line shares one currency (never a
    # wrong cross-FX sum). margins[i] is None when a rate is missing or currencies differ.
    lines = opp.staffed or []
    margins = [margin_of(ln) for ln in lines]
    for ln, m in zip(d.get("staffed", []), margins):
        ln["margin"] = m
    # Total only when EVERY line has a margin AND one shared, non-empty currency (a line with no/
    # unknown currency taints the sum — never a wrong cross-FX or unit-less total).
    ccys = {(ln.get("currency") or "").strip().upper() for ln in lines}
    if lines and "" not in ccys and len(ccys) == 1 and all(m is not None for m in margins):
        d["total_margin"] = round(sum(margins), 2)
        d["margin_currency"] = next(iter(ccys))
    else:
        d["total_margin"] = None
        d["margin_currency"] = ""
    return d


def _opp_consultants(opp) -> list:
    return _load_consultants([ln.get("consultant_id") for ln in (opp.staffed or [])])


@app.post("/api/opportunities")
def create_opportunity(req: OpportunityCreate) -> JSONResponse:
    """Start pursuing a project. Idempotent for ingested postings: a re-surfaced (source,
    source_uid) returns the existing opportunity instead of duplicating it."""
    project, has_input = _project_from_request(req)
    if not has_input:
        raise HTTPException(status_code=400, detail="Describe the project (a title, brief, or job).")
    job = req.job if isinstance(req.job, dict) else None
    source = ((job or {}).get("source") or "").strip()
    source_uid = ((job or {}).get("source_uid") or (job or {}).get("id") or "").strip()
    existing = store.get_opportunity_by_posting(source, source_uid) if source_uid else None
    if existing is not None:
        return JSONResponse(_opp_payload(existing))     # idempotent: don't duplicate the posting
    proj = {"title": project.title, "description": project.description, "skills": project.skills,
            "location": project.location, "source": source, "source_uid": source_uid,
            "url": project.url, "rate_ceiling": project.rate_ceiling, "currency": project.currency,
            "start_date": project.start_date}
    opp = new_opportunity(proj, kind=req.kind if req.kind in ("posting", "warm") else "posting")
    if req.consultant_ids:
        set_staffing(opp, _staff_lines(req.consultant_ids))
    store.save_opportunity(opp)
    return JSONResponse(_opp_payload(opp))


@app.get("/api/opportunities")
def list_opportunities() -> dict:
    return {"opportunities": [_opp_payload(o) for o in store.list_opportunities()],
            "statuses": OPP_STATUSES, "suggested_next": OPP_SUGGESTED_NEXT}


@app.get("/api/opportunities/{oid}")
def get_opportunity(oid: str) -> JSONResponse:
    opp = store.get_opportunity(oid)
    if opp is None:
        raise HTTPException(status_code=404, detail="Opportunity not found.")
    return JSONResponse(_opp_payload(opp))


@app.patch("/api/opportunities/{oid}")
def update_opportunity(oid: str, upd: OpportunityUpdate) -> JSONResponse:
    opp = store.get_opportunity(oid)
    if opp is None:
        raise HTTPException(status_code=404, detail="Opportunity not found.")
    if upd.status is not None:
        try:
            set_opp_status(opp, upd.status)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    if upd.staffed is not None:
        set_staffing(opp, upd.staffed)
    if upd.notes is not None:
        opp.notes = upd.notes
    if upd.rate_ceiling is not None:
        opp.rate_ceiling = upd.rate_ceiling
    if upd.currency is not None:
        opp.currency = upd.currency.strip()
    if upd.start_date is not None:
        opp.start_date = upd.start_date.strip()
    if upd.client_id is not None:
        opp.client_id = upd.client_id.strip()
    opp.updated = time.time()
    store.save_opportunity(opp)
    return JSONResponse(_opp_payload(opp))


@app.delete("/api/opportunities/{oid}")
def delete_opportunity(oid: str) -> dict:
    store.delete_opportunity(oid)
    return {"ok": True}


def _do_not_bid_client(opp):
    """The linked client if this opportunity is for a do-not-bid account, else None. Enforces the
    do_not_bid guardrail at the bid-production points (a UI badge alone never blocked anything)."""
    if getattr(opp, "client_id", ""):
        c = store.get_client(opp.client_id)
        if c is not None and c.do_not_bid:
            return c
    return None


def _block_do_not_bid(opp, override: bool):
    """Raise 409 for a do-not-bid client unless explicitly overridden. Returns the offending client
    when overridden (so the caller can audit it on its own persisted save), else None."""
    dnb = _do_not_bid_client(opp)
    if dnb is not None and not override:
        raise HTTPException(status_code=409, detail={
            "message": f"Client “{dnb.name}” is marked do-not-bid. Re-submit with override to proceed.",
            "do_not_bid": True, "client": dnb.name})
    return dnb


@app.post("/api/opportunities/{oid}/proposal")
def generate_opportunity_proposal(oid: str, req: OpportunityProposalRequest) -> JSONResponse:
    """Draft a proposal INTO the opportunity, run the QA gate, and persist the artifact + QA +
    an audit event. Never sends — a human exports and submits."""
    opp = store.get_opportunity(oid)
    if opp is None:
        raise HTTPException(status_code=404, detail="Opportunity not found.")
    dnb = _block_do_not_bid(opp, req.override_do_not_bid)         # do-not-bid guardrail
    if dnb is not None:
        record_event(opp, "do_not_bid_override", f"Drafted despite do-not-bid client “{dnb.name}”")
    ids = req.consultant_ids if req.consultant_ids else [ln.get("consultant_id") for ln in (opp.staffed or [])]
    consultants = _load_consultants(ids)
    if not consultants:
        raise HTTPException(status_code=400, detail="Staff at least one consultant before drafting.")
    if req.consultant_ids:                                  # explicit selection (re)staffs the bid
        set_staffing(opp, _staff_lines(req.consultant_ids))
    project = Project(title=opp.title, description=opp.description, skills=opp.skills,
                      location=opp.location, rate_ceiling=opp.rate_ceiling, currency=opp.currency,
                      start_date=opp.start_date, source=opp.source, url=opp.url)
    redact = settings.redact_pii_default if req.redact_pii is None else bool(req.redact_pii)
    options = ProposalOptions(tone=req.tone, length=req.length, use_llm=req.use_llm, redact_pii=redact)
    house = store.get_house() or House()
    examples = [e["text"] for e in store.list_examples()]
    draft = generate_proposal(house, project, consultants, options, examples=examples)
    findings = check_proposal(draft.body, consultants)
    attach_proposal(opp, draft.subject, draft.body, draft.generator, findings, has_blocking(findings))
    store.save_opportunity(opp)
    return JSONResponse({"opportunity": _opp_payload(opp), "qa": findings,
                         "blocking": has_blocking(findings), "used_llm": options.use_llm and llm_available()})


@app.get("/api/opportunities/{oid}/export")
def export_opportunity_proposal(oid: str, override_do_not_bid: bool = False) -> PlainTextResponse:
    """Export the opportunity's stored proposal — enforces the do-not-bid guardrail, re-runs the QA
    gate (409 if blocking), and logs a human-export audit event."""
    opp = store.get_opportunity(oid)
    if opp is None:
        raise HTTPException(status_code=404, detail="Opportunity not found.")
    dnb = _block_do_not_bid(opp, override_do_not_bid)         # do-not-bid guardrail
    body = (opp.proposal_body or "").strip()
    if not body:
        raise HTTPException(status_code=400, detail="No proposal drafted yet.")
    findings = check_proposal(body, _opp_consultants(opp))
    if has_blocking(findings):
        raise HTTPException(status_code=409, detail={
            "message": "This proposal didn't pass the fabrication check — fix the flagged items before export.",
            "findings": findings})

    def _finish(o):                                          # audit: a human took it from here
        if dnb is not None:
            record_event(o, "do_not_bid_override", f"Exported despite do-not-bid client “{dnb.name}”")
        record_export(o)
    store.update_opportunity(oid, _finish)
    safe = "".join(c if c.isalnum() or c in " -_" else "" for c in opp.title).strip()
    filename = (safe or "proposal")[:60].replace(" ", "_") + ".txt"
    subject = (opp.proposal_subject or "").strip()
    content = (f"Subject: {subject}\n\n{body}\n" if subject else f"{body}\n")
    return PlainTextResponse(content, headers={"Content-Disposition": f'attachment; filename="{filename}"'})


# ---------------------------------------------------------------------------
# Clients (the direct-warm relationship layer)
# ---------------------------------------------------------------------------

@app.post("/api/clients")
def create_client(req: ClientCreate) -> JSONResponse:
    c = new_client(req.name or "", sector=req.sector or "", contacts=req.contacts or [],
                   do_not_bid=bool(req.do_not_bid),
                   past_projects=_clean_list(req.past_projects, cap=50) if req.past_projects else [],
                   notes=req.notes or "")
    store.save_client(c)
    return JSONResponse(c.to_dict())


@app.get("/api/clients")
def list_clients() -> dict:
    return {"clients": [c.to_dict() for c in store.list_clients()]}


@app.get("/api/clients/{cid}")
def get_client(cid: str) -> JSONResponse:
    c = store.get_client(cid)
    if c is None:
        raise HTTPException(status_code=404, detail="Client not found.")
    return JSONResponse(c.to_dict())


@app.patch("/api/clients/{cid}")
def update_client(cid: str, upd: ClientUpdate) -> JSONResponse:
    from .clients import _clean_contacts
    c = store.get_client(cid)
    if c is None:
        raise HTTPException(status_code=404, detail="Client not found.")
    if upd.name is not None:
        c.name = upd.name.strip() or c.name
    if upd.sector is not None:
        c.sector = upd.sector.strip()
    if upd.contacts is not None:
        c.contacts = _clean_contacts(upd.contacts)
    if upd.do_not_bid is not None:
        c.do_not_bid = bool(upd.do_not_bid)
    if upd.past_projects is not None:
        c.past_projects = _clean_list(upd.past_projects, cap=50)
    if upd.notes is not None:
        c.notes = upd.notes
    c.updated = time.time()
    store.save_client(c)
    return JSONResponse(c.to_dict())


@app.delete("/api/clients/{cid}")
def delete_client(cid: str) -> dict:
    store.delete_client(cid)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Case studies (grounded proof / delivered engagements)
# ---------------------------------------------------------------------------

def _apply_case_study_fields(cs: CaseStudy, data: dict) -> None:
    from .case_studies import _clean_outcomes
    str_fields = {"title", "client_name", "client_anonymized", "sector", "summary",
                  "reference_contact", "start_date", "end_date", "notes"}
    for k, v in data.items():
        if v is None:
            continue
        if k in str_fields:
            setattr(cs, k, str(v).strip())
        elif k == "outcomes":
            cs.outcomes = _clean_outcomes(v)
        elif k in ("skills", "consultant_ids"):
            setattr(cs, k, _clean_list(v, lower=(k == "skills")))
        elif k == "disclosure":
            vv = str(v).strip().lower()
            if vv in DISCLOSURE:
                cs.disclosure = vv
        elif k == "reference_consent":
            cs.reference_consent = bool(v)
    if not (cs.title or "").strip():
        cs.title = "Untitled engagement"
    cs.updated = time.time()


@app.post("/api/case-studies")
def create_case_study(req: CaseStudyCreate) -> JSONResponse:
    cs = new_case_study(req.title or "")
    _apply_case_study_fields(cs, req.model_dump())
    store.save_case_study(cs)
    return JSONResponse(cs.to_dict())


@app.get("/api/case-studies")
def list_case_studies() -> dict:
    return {"case_studies": [cs.to_dict() for cs in store.list_case_studies()],
            "disclosure_levels": list(DISCLOSURE)}


@app.get("/api/case-studies/{csid}")
def get_case_study(csid: str) -> JSONResponse:
    cs = store.get_case_study(csid)
    if cs is None:
        raise HTTPException(status_code=404, detail="Case study not found.")
    return JSONResponse(cs.to_dict())


@app.patch("/api/case-studies/{csid}")
def update_case_study(csid: str, upd: CaseStudyUpdate) -> JSONResponse:
    cs = store.get_case_study(csid)
    if cs is None:
        raise HTTPException(status_code=404, detail="Case study not found.")
    _apply_case_study_fields(cs, upd.model_dump())
    store.save_case_study(cs)
    return JSONResponse(cs.to_dict())


@app.delete("/api/case-studies/{csid}")
def delete_case_study(csid: str) -> dict:
    store.delete_case_study(csid)
    return {"ok": True}


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
    if store.update_saved_search(sid, mark_seen) is None:    # atomic vs a concurrent sweep/run
        raise HTTPException(status_code=404, detail="Saved search not found.")
    return {"ok": True, "new_count": 0}


def _run_one(s) -> dict:
    """Run a saved search; update its seen-set/new_count; return the ranked jobs + new ids."""
    profile = store.get_profile(s.cv_id) if s.cv_id else None
    if profile is None:
        raise HTTPException(status_code=400,
                            detail="The CV for this saved search isn't available — re-upload your CV.")
    settings_ = _build_settings(s.keywords, s.location, s.sources, s.limit_per_source,
                                s.remote, s.days, s.semantic, s.min_score, getattr(s, "gigs_only", False))
    result = find_jobs(profile, settings_)
    # atomic diff + seen-set update so a concurrent background sweep can't clobber it
    box = {"new": []}
    def _diff(sv):
        box["new"] = register_run(sv, [j.id for j in result.jobs])
    updated = store.update_saved_search(s.id, _diff) or s
    return {
        "jobs": [j.to_dict() for j in result.jobs],
        "new_ids": box["new"],
        "new_count": updated.new_count,
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


# ---------------------------------------------------------------------------
# Notifications inbox + opt-in background alerts
# ---------------------------------------------------------------------------

class AlertsConfig(BaseModel):
    enabled: bool | None = None
    interval_hours: int | None = None


@app.get("/api/notifications")
def list_notifications() -> dict:
    notes = store.list_notifications()
    return {"notifications": [n.to_dict() for n in notes],
            "unread": sum(1 for n in notes if not n.read)}


@app.post("/api/notifications/read")
def mark_all_notifications_read() -> dict:
    for n in store.list_notifications():
        if not n.read:
            n.read = True
            store.save_notification(n)
    return {"ok": True, "unread": 0}


@app.post("/api/notifications/{nid}/read")
def mark_notification_read(nid: str) -> dict:
    n = store.get_notification(nid)
    if n is None:
        raise HTTPException(status_code=404, detail="Notification not found.")
    n.read = True
    store.save_notification(n)
    return {"ok": True}


@app.delete("/api/notifications/{nid}")
def dismiss_notification(nid: str) -> dict:
    store.delete_notification(nid)
    return {"ok": True}


@app.get("/api/alerts/config")
def get_alerts_config() -> dict:
    return alert_scheduler.status()


@app.post("/api/alerts/config")
def set_alerts_config(req: AlertsConfig) -> dict:
    alerts.set_prefs(enabled=req.enabled, interval_hours=req.interval_hours)
    alert_scheduler.start()          # ensure the loop is live so it can act on the new pref
    return alert_scheduler.status()


@app.post("/api/alerts/run-now")
def run_alerts_now() -> dict:
    """User-triggered immediate sweep (re-runs saved searches + refreshes reminders)."""
    return alert_scheduler.run_now()


# ---------------------------------------------------------------------------
# Data rights — export everything / delete everything
# ---------------------------------------------------------------------------

@app.get("/api/export")
def export_all_data() -> JSONResponse:
    """Download a full local backup of everything stored (no API keys — those live
    outside the database)."""
    bundle = {"app": "Job Finder", "version": __version__,
              "exported_at": time.time(), "data": store.export_all()}
    return JSONResponse(bundle, headers={
        "Content-Disposition": 'attachment; filename="jobfinder-export.json"'})


@app.post("/api/data/delete-all")
def delete_all_data() -> dict:
    """Permanently delete all stored user data on this machine. API keys (Settings) are
    not affected. Same-origin is enforced by the security middleware, so a stray site
    can't trigger this."""
    snap = store.export_all()
    counts = {
        "profiles": len(snap.get("profiles") or {}),
        "applications": len(snap.get("applications") or []),
        "saved_searches": len(snap.get("saved_searches") or []),
        "examples": len(snap.get("examples") or []),
        "notifications": len(snap.get("notifications") or []),
    }
    # hold the sweep lock so an in-flight background sweep can't re-insert just-deleted rows
    with alert_scheduler.paused():
        store.delete_all()
    return {"ok": True, "deleted": counts}


# Static assets (css/js)
app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")
