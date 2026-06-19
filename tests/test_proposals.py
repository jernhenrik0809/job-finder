"""Tests for the house-PROPOSAL path: the offline guardrail gate (``guardrails.check_proposal`` /
``has_blocking``), the deterministic offline template generator (``proposals.generate_template`` /
``generate_proposal`` with ``use_llm=False``), and the two proposal endpoints.

Two groups:
  (A) UNIT — import the modules directly, no server, no network, no API key.
  (B) ENDPOINT — drive the FastAPI app via TestClient, exactly like ``tests/test_bench_web.py``.

State note (mirrors test_bench_web.py): the suite runs against a process-global in-memory store
(forced by conftest), so endpoint rows persist across tests in this run. Each endpoint test seeds
its OWN consultant and asserts on what it created, cleaning up by id afterwards.

Everything here is deterministic and offline: ``ProposalOptions(use_llm=False)`` selects the
template generator, which makes no network calls and needs no ANTHROPIC_API_KEY.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from jobfinder.bench import Project
from jobfinder.consultants import Consultant
from jobfinder.guardrails import check_proposal, has_blocking
from jobfinder.house import House
from jobfinder.proposals import ProposalOptions, generate_proposal, generate_template
from jobfinder.web import app

client = TestClient(app)


# ===========================================================================
# (A) UNIT — guardrails.check_proposal / has_blocking
# ===========================================================================

def _types(findings):
    return {f["type"] for f in findings}


def test_grounded_body_has_no_findings():
    # A capability claim that is fully backed by the consultant's REAL skills -> clean.
    c = Consultant(name="Anna", skills=["python", "django"])
    findings = check_proposal("Anna has deep Python expertise and strong Django skills.", [c])
    assert findings == []
    assert has_blocking(findings) is False


def test_grounded_body_accepts_plain_dict_consultants():
    # The gate accepts plain {name, skills} dicts as well as Consultant objects.
    findings = check_proposal(
        "Our consultant has extensive Python experience.",
        [{"name": "Anna", "skills": ["python"]}],
    )
    assert findings == []
    assert has_blocking(findings) is False


def test_unsupported_capability_blocks():
    # The consultant has python; the body claims Kubernetes, which nobody proposed has -> blocking.
    c = Consultant(name="Anna", skills=["python"])
    findings = check_proposal("Our consultant has deep Kubernetes expertise.", [c])
    assert "unsupported_capability" in _types(findings)
    f = next(f for f in findings if f["type"] == "unsupported_capability")
    assert f["blocking"] is True
    assert "kubernetes" in [i.lower() for i in f["items"]]
    assert has_blocking(findings) is True


def test_no_grounding_fails_closed_on_empty_skills():
    # A capability claim while the only proposed consultant has NO recorded skills -> fail closed.
    c = Consultant(name="Anna", skills=[])
    findings = check_proposal("Our consultant has deep Kubernetes expertise.", [c])
    assert "no_grounding" in _types(findings)
    f = next(f for f in findings if f["type"] == "no_grounding")
    assert f["blocking"] is True
    assert has_blocking(findings) is True


def test_placeholder_blocks():
    c = Consultant(name="Anna", skills=["python"])
    findings = check_proposal("We are pleased to submit this bid for [Company].", [c])
    assert "placeholder" in _types(findings)
    f = next(f for f in findings if f["type"] == "placeholder")
    assert f["blocking"] is True
    assert "[Company]" in f["items"]
    assert has_blocking(findings) is True


def test_misattributed_skill_names_the_wrong_consultant():
    # Two consultants: kubernetes IS on the team (via Bo) but is attributed to Anna, who lacks it.
    # The consultant's first name sits well within the ~90-char attribution window before the skill.
    anna = Consultant(name="Anna", skills=["python"])
    bo = Consultant(name="Bo", skills=["kubernetes"])
    findings = check_proposal("Anna has deep Kubernetes expertise.", [anna, bo])
    assert "misattributed_skill" in _types(findings), findings
    f = next(f for f in findings if f["type"] == "misattributed_skill")
    assert f["blocking"] is True
    # the finding names anna against the misattributed kubernetes skill
    assert any("anna" in i.lower() and "kubernetes" in i.lower() for i in f["items"]), f["items"]
    assert has_blocking(findings) is True


def test_danish_possession_cue_blocks():
    # Danish possession cue ("ekspert i") + a skill nobody has -> unsupported_capability, blocking.
    c = Consultant(name="Anna", skills=["python"])
    findings = check_proposal("Vores konsulent er ekspert i Kubernetes.", [c])
    assert "unsupported_capability" in _types(findings), findings
    f = next(f for f in findings if f["type"] == "unsupported_capability")
    assert f["blocking"] is True
    assert has_blocking(findings) is True


def test_empty_body_has_no_findings():
    c = Consultant(name="Anna", skills=["python"])
    assert check_proposal("", [c]) == []
    assert has_blocking(check_proposal("", [c])) is False


# ===========================================================================
# (A) UNIT — proposals.generate_template / generate_proposal (offline path)
# ===========================================================================

def test_template_proposal_is_grounded_and_complete():
    house = House(name="Northwind Consulting")
    project = Project(title="Senior Python Engineer",
                      description="Build and ship Django REST APIs on AWS.",
                      skills=["python", "django", "aws"])
    c = Consultant(name="Anna Jensen", skills=["python", "django", "aws"], title="Python Engineer")

    draft = generate_proposal(house, project, [c], ProposalOptions(use_llm=False))

    assert draft.generator == "template"          # no key in tests -> offline template path
    assert draft.body.strip()                      # non-empty body
    assert draft.subject.strip()                   # has a subject line
    assert "Anna Jensen" in draft.body             # mentions the consultant's name
    assert "Northwind Consulting" in draft.body    # mentions the house name
    assert draft.consultant_ids == [c.id]
    assert draft.consultant_names == ["Anna Jensen"]


def test_template_proposal_passes_the_guardrail_gate():
    # The template grounds bios only in skills the consultant actually has, so a proposal it
    # produces must PASS check_proposal (no blocking findings) — the gate and generator agree.
    house = House(name="Northwind Consulting")
    project = Project(title="Kubernetes Platform Engineer",
                      description="Run a Kubernetes platform.",
                      skills=["kubernetes", "terraform"])
    # consultant deliberately does NOT have the project's skills — template must not fabricate them.
    c = Consultant(name="Anna Jensen", skills=["python", "django"], title="Backend Engineer")

    draft = generate_template(house, project, [c], ProposalOptions(use_llm=False))
    findings = check_proposal(draft.body, [c])
    assert has_blocking(findings) is False, findings


def test_generate_template_is_directly_callable():
    # generate_template (the offline entry point) returns a template draft without any LLM path.
    house = House(name="Acme Bench")
    project = Project(title="Data Engineer", skills=["python"])
    c = Consultant(name="Bo Hansen", skills=["python", "sql"])
    draft = generate_template(house, project, [c], ProposalOptions(use_llm=False))
    assert draft.generator == "template"
    assert "Bo Hansen" in draft.body and "Acme Bench" in draft.body


# ===========================================================================
# (B) ENDPOINT — POST /api/proposals/generate and /api/proposals/export
# ===========================================================================

def _create_consultant(**body) -> dict:
    r = client.post("/api/consultants", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def _delete_consultant(cid: str) -> None:
    client.delete(f"/api/consultants/{cid}")


def test_generate_endpoint_returns_clean_grounded_template():
    c = _create_consultant(name="Anna Jensen", text="Senior Python Engineer\nSkills: Python, Django, AWS.",
                           skills=["python", "django", "aws"], title="Python Engineer")
    try:
        r = client.post("/api/proposals/generate", json={
            "title": "Senior Python Engineer",
            "description": "Build Django REST APIs on AWS.",
            "skills": ["python", "django", "aws"],
            "consultant_ids": [c["id"]],
        })
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["blocking"] is False               # template is grounded
        assert data["used_llm"] is False               # no API key in tests
        assert data["proposal"]["body"].strip()        # non-empty body
        assert data["proposal"]["generator"] == "template"
        assert c["id"] in data["proposal"]["consultant_ids"]
    finally:
        _delete_consultant(c["id"])


def test_generate_endpoint_requires_a_consultant():
    # A project but no consultant_ids -> 400.
    r = client.post("/api/proposals/generate", json={
        "title": "Senior Python Engineer", "skills": ["python"], "consultant_ids": [],
    })
    assert r.status_code == 400


def test_generate_endpoint_requires_a_project():
    # A consultant but no project title/description -> 400 (checked before the consultant check).
    c = _create_consultant(name="Anna Jensen", skills=["python"])
    try:
        r = client.post("/api/proposals/generate", json={"consultant_ids": [c["id"]]})
        assert r.status_code == 400
    finally:
        _delete_consultant(c["id"])


def test_export_endpoint_exports_a_clean_body():
    c = _create_consultant(name="Anna Jensen", text="Senior Python Engineer\nSkills: Python, Django, AWS.",
                           skills=["python", "django", "aws"], title="Python Engineer")
    try:
        gen = client.post("/api/proposals/generate", json={
            "title": "Senior Python Engineer",
            "description": "Build Django REST APIs on AWS.",
            "skills": ["python", "django", "aws"],
            "consultant_ids": [c["id"]],
        })
        assert gen.status_code == 200, gen.text
        proposal = gen.json()["proposal"]

        r = client.post("/api/proposals/export", json={
            "subject": proposal["subject"],
            "body": proposal["body"],
            "project_title": "Senior Python Engineer",
            "consultant_ids": [c["id"]],
        })
        assert r.status_code == 200, r.text
        assert "attachment" in r.headers.get("content-disposition", "")
        assert r.text.strip()                          # non-empty exported text
        assert "Anna Jensen" in r.text                 # the grounded body carried through
    finally:
        _delete_consultant(c["id"])


def test_export_endpoint_blocks_a_fabricated_body_with_409():
    # The consultant has no Kubernetes; a body claiming it is a fabrication -> 409, with the
    # unsupported_capability finding surfaced in detail.findings.
    c = _create_consultant(name="Anna Jensen", skills=["python", "django"], title="Python Engineer")
    try:
        fabricated = ("Dear hiring team,\n\nNorthwind Consulting puts forward Anna Jensen, who has "
                      "deep Kubernetes expertise and years of Terraform experience.\n\nKind regards,\n"
                      "Northwind Consulting")
        r = client.post("/api/proposals/export", json={
            "subject": "Proposal", "body": fabricated,
            "project_title": "Platform Engineer", "consultant_ids": [c["id"]],
        })
        assert r.status_code == 409, r.text
        findings = r.json()["detail"]["findings"]
        assert "unsupported_capability" in {f["type"] for f in findings}, findings
    finally:
        _delete_consultant(c["id"])


def test_export_endpoint_rejects_an_empty_body():
    r = client.post("/api/proposals/export", json={"body": "", "consultant_ids": []})
    assert r.status_code == 400


# --- regression tests for the adversarial-review fixes (v1.30.0) -----------

def test_qa_blocks_action_verb_phrasing():
    """A fabrication phrased as an action ('will handle the Kubernetes cluster') must block,
    not just adjectival possession cues. Regression for the cue-bypass finding."""
    from jobfinder.guardrails import check_proposal, has_blocking
    from jobfinder.consultants import Consultant
    f = check_proposal("Proposed team\n- Anna will handle the Kubernetes cluster and implement the Rust services.",
                       [Consultant(name="Anna", skills=["python"])])
    assert has_blocking(f) and any(x["type"] == "unsupported_capability" for x in f)


def test_qa_handles_non_list_skills_without_crash():
    """A consultant whose skills field is a stray string must not crash or create char-skills —
    it collapses to no skills, so a claim fails closed (no_grounding)."""
    from jobfinder.guardrails import check_proposal, has_blocking
    from jobfinder.consultants import Consultant
    f = check_proposal("Anna is an expert in Python.", [Consultant(name="Anna", skills="python")])
    assert has_blocking(f) and any(x["type"] == "no_grounding" for x in f)


def test_qa_name_match_is_word_bounded():
    """A short first name ('Per') must not match inside 'performed' and spuriously misattribute."""
    from jobfinder.guardrails import check_proposal, has_blocking
    from jobfinder.consultants import Consultant
    f = check_proposal("The team performed deep Kubernetes work.",
                       [Consultant(name="Per", skills=["kubernetes"])])
    assert not has_blocking(f)          # Per has kubernetes; 'per' in 'performed' must not anchor


def test_template_output_passes_its_own_qa_gate():
    """The offline template must never produce output its own QA gate blocks — it neither echoes
    the client brief nor lists required skills as claims. Regression for the self-block finding."""
    from jobfinder.guardrails import check_proposal, has_blocking
    from jobfinder.consultants import Consultant
    from jobfinder.house import House
    from jobfinder.bench import Project
    from jobfinder.proposals import generate_proposal, ProposalOptions
    anna = Consultant(name="Anna Hansen", title="Cloud lead", skills=["python"])
    proj = Project(title="Cloud lead", skills=["python", "kubernetes", "terraform"],
                   description="We need an expert in Kubernetes and Rust.")
    d = generate_proposal(House(name="Nordic"), proj, [anna], ProposalOptions(use_llm=False))
    assert not has_blocking(check_proposal(d.body, [anna]))
