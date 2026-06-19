# Example consulting house (for the document-engine build brief)

**Fictional** sample data for building/testing the document-generation engine (see
[`../proposal-doc-engine-brief.md`](../proposal-doc-engine-brief.md)). It mirrors the real
entity shapes (`jobfinder/house.py`, `jobfinder/consultants.py`, `jobfinder/opportunities.py`,
`jobfinder/bench.py:Project`) so a builder can load it directly.

| File | Contents |
|---|---|
| `house.json` | **Nordlys Consulting** — the house identity (name, voice, signatory, boilerplate, contact). |
| `consultants.json` | three bench consultants — **Anna Berg** (Senior Cloud & Data Engineer), **Lars Holm** (Solution Architect, .NET/Azure), **Mette Nielsen** (Data Scientist / ML) — each with skills, availability, day rates (DKK), and a full CV in `raw_text`. |
| `opportunity.json` | a sample gig (**"Cloud migration & data platform — Danish fintech"**) with staffed bid lines (Anna + Mette) and a ready, **QA-passing** `proposal_body`. |

**Important:** `opportunity.json.proposal_body` is grounded ONLY in Anna's and Mette's real CVs and
**passes `guardrails.check_proposal` with no blocking findings**. The document engine must render
this text faithfully — it may lay it out and brand it, but it must **not introduce any new fact or
capability claim** at render time. To re-verify:

```python
import json
from jobfinder.consultants import Consultant
from jobfinder.guardrails import check_proposal, has_blocking
cons = [Consultant.from_dict(c) for c in json.load(open("docs/examples/consultants.json"))]
opp = json.load(open("docs/examples/opportunity.json"))
proposed = [c for c in cons if c.id in {l["consultant_id"] for l in opp["staffed"]}]
assert not has_blocking(check_proposal(opp["proposal_body"], proposed))   # passes today
```

The expected example output is a branded, client-ready **proposal PDF** for Nordlys Consulting
plus **one-pager CVs** for Anna and Mette — see the build brief for the document set and acceptance
criteria.
