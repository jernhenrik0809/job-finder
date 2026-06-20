# Design task: print-ready HTML/CSS for a consulting proposal + a consultant one-pager

You're designing two **print-ready, brand-parameterised HTML documents** for a small Danish
consulting house. A separate program fills them with data and converts them to **PDF via
WeasyPrint** — so this is a **paged-media HTML/CSS** task, not a web page. Everything you need is in
this message; you don't need any repo or external resource.

## What to deliver (and the boundary)

Deliver **two self-contained HTML files**, each with **all CSS inline in a `<style>` block**:

1. `proposal.html` — a consulting **proposal** (multi-page A4).
2. `one-pager.html` — a single-page A4 **consultant CV one-pager**.

Render them filled with the **example content below** so the design is visually reviewable. Use the
brand values as **`:root` CSS custom properties** so they can be swapped per house. After each file,
add a short **"slot → field" table** mapping each dynamic piece of text to the data field it comes
from (so the program can templatise it mechanically).

**You produce HTML + CSS only.** Do **not** write Python, fetch anything, or use JavaScript. The
program handles data-filling, the HTML→PDF conversion, and a separate fabrication check.

## Hard rules (non-negotiable — the documents go out under the house's name)

- **Render only the facts you're given.** Never invent or embellish outcomes, clients, metrics,
  skills, dates, or rates. Every fact is a plain text node sourced from a field (see the slot tables).
- **Never show internal fields.** The data model has fields like `cost_rate`, margin,
  `engagement_type`, `rate_ceiling` — these must **never** appear in either document. Show only the
  **sell rate** (the billable day rate).
- **Respect client anonymity.** A case study may be `anonymized_only` — then show the **anonymized
  descriptor** ("a Danish pension provider"), never the real client name.
- **No remote assets.** No CDN, no Google Fonts, no `@import` of remote CSS, no external images.
  Fonts must be a **local/websafe stack** (reference by family name; the program bundles the actual
  font files). The logo is a local file path / inline SVG placeholder.
- **No JavaScript.**
- **Visibly mark the document `DRAFT`** (e.g. a subtle banner or watermark) — these are reviewed and
  sent by a human, never auto-sent.

## Make it WeasyPrint- and PDF/UA-friendly

- **Paged media:** `@page { size: A4; margin: ... }`; running header/footer via
  `@page { @top-center {...} @bottom-right {...} }` with `content: "Page " counter(page) " of " counter(pages);`.
- **Page-break control:** `break-inside: avoid` on team-bio blocks, table rows, and the cover;
  `orphans: 3; widows: 3;`. Cover page on its own (`break-after: page`).
- **Accessibility (this is a public-sector/tender requirement):** use **real semantic heading levels
  in order** (`<h1>` once, then `<h2>`/`<h3>`), set the document language (`<html lang="da">` for the
  Danish example), use a real `<table>` with `<thead>`/`<th scope="col">` for pricing, give the logo
  meaningful `alt`, and **don't** use tables for page layout. Restrained, accessible colour contrast.
- **Tone & restraint (Danish business norm):** clean, understated, **not over-designed** — one
  primary colour + one accent, generous whitespace, no gradients/multi-font clutter. It should read
  as senior and trustworthy, scannable in ~30 seconds per section.

## Brand — use these `:root` custom properties (defaults; the house tunes them later)

```css
:root{
  --brand:#1f3a5f;      /* deep Nordic blue (primary) */
  --accent:#c9772e;     /* warm amber (sparing accents only) */
  --ink:#1a1a1a; --muted:#5f5e5a; --hairline:#d9d7cf; --paper:#ffffff;
  --font-heading:"Georgia", serif;       /* placeholder; real fonts bundled locally */
  --font-body:"Helvetica Neue", Arial, sans-serif;
  --page-margin:22mm;
}
```

---

## EXAMPLE CONTENT TO RENDER

### House (brand identity — header/footer/cover)
- **Name:** Nordlys Consulting
- **Tagline:** Senior Nordic engineering consultants, delivered hands-on.
- **Signatory:** Søren Dahl, Partner
- **Contact:** kontakt@nordlys-consulting.example · +45 12 34 56 78 · Refshalevej 100, 1432 København K
- **Website:** nordlys-consulting.example
- **Logo:** (no asset yet — use a tasteful wordmark/monogram placeholder, e.g. a "◆ Nordlys" lockup)

### Document A — `proposal.html`
**Cover:** house wordmark; title "Proposal"; project title **"Cloud migration & data platform"**;
recipient line "Prepared for: the client" (placeholder); date 20 June 2026; a **DRAFT** marker; a
small validity/confidentiality line ("Valid 30 days · Confidential").

**Body — render this text verbatim, each labelled heading as its own `<h2>` section** (this is the
program's QA-approved prose; lay it out, don't reword it):

> **Understanding of the engagement**
> You are moving an on-prem data stack to AWS and need a dependable, GDPR-compliant platform —
> containerised services on Kubernetes, infrastructure-as-code, and resilient ingestion pipelines
> feeding analytics — with a later document-classification phase. You want senior, Danish-speaking
> consultants who integrate with your team and work hybrid from Copenhagen.
>
> **Proposed team** *(render each consultant as a distinct bio block — name + role as a subheading,
> then the text)*
> - **Anna Berg, Senior Cloud & Data Engineer (9 years).** Relevant experience with AWS, Kubernetes,
>   Terraform, Python, Kafka and Airflow. At Danske Pension she built a GDPR-compliant data platform
>   on AWS (EKS + Terraform) ingesting 2M+ events/day and cut nightly batch runtime from 6h to 40min.
>   Available from 1 August 2026.
> - **Mette Nielsen, Data Scientist / ML Engineer (7 years),** for the document-classification phase.
>   Relevant experience with Python, NLP and MLOps; at Saxo Bank she built a document-classification
>   service that cut manual triage by ~60%. Available from 1 September 2026, aligned with the later phase.
>
> **Approach**
> We propose a two-phase delivery: (1) migrate and harden the platform — infrastructure-as-code on
> AWS, Kubernetes for the services, and resilient ingestion — with security review built into each
> milestone; (2) add the document-classification capability once the platform is stable. We work in
> two-week iterations with a demo at the end of each, and integrate directly with your engineers so
> the capability stays in-house after we leave.
>
> **Next steps**
> We would welcome a short call to align on scope, timeline and on-site days. We can share Anna's and
> Mette's full CVs and client references on request.

**Relevant proof** *(render as a small "selected outcome" block — the program supplies grounded case
studies; here is one, already anonymised):*
- **GDPR data platform — a Danish pension provider.** Outcome: **nightly batch runtime cut from 6h to
  40min.** (Delivered by Anna Berg.)  *(Note: client shown anonymised — never print a real name when
  the disclosure is anonymised.)*

**Pricing** *(render as a real `<table>`; show the sell rate only, single currency):*

| Consultant | Role | Day rate | Availability |
|---|---|---|---|
| Anna Berg | Senior Cloud & Data Engineer | DKK 1,150 | from 1 Aug 2026 |
| Mette Nielsen | Data Scientist / ML Engineer | DKK 1,100 | from 1 Sep 2026 |

**Why Nordlys** *(short, grounded):* "Nordlys Consulting fields senior, hands-on consultants who
integrate quickly and focus on outcomes."

**Sign-off:** Kind regards, **Søren Dahl, Partner — Nordlys Consulting.**

### Document B — `one-pager.html` (render TWO examples: Anna, then Mette — one A4 page each)

**Anna Berg**
- **Header:** Anna Berg · Senior Cloud & Data Engineer · København · Danish, English
- **Relevant skills:** AWS, Kubernetes, Terraform, Python, Kafka, Airflow, PostgreSQL, GDPR
- **Selected experience** *(from CV — contact details already redacted; render as-is):*
  - *Lead Data Engineer — Danske Pension (2022–2024):* built a GDPR-compliant data platform on AWS
    (EKS + Terraform) ingesting 2M+ events/day; cut nightly batch runtime from 6h to 40min.
  - *Senior Backend Engineer — Trustpilot (2018–2022):* owned review-ingestion microservices (Python)
    at 30M+ req/day; led a 40-service Kubernetes migration with zero customer-facing downtime.
- **Certifications:** AWS Certified Solutions Architect – Associate · **Clearance:** EU work permit
- **Availability:** from 1 August 2026 · **Day rate:** DKK 1,150

**Mette Nielsen**
- **Header:** Mette Nielsen · Data Scientist / ML Engineer · København · Danish, English
- **Relevant skills:** Python, scikit-learn, PyTorch, NLP, MLOps, pandas, AWS
- **Selected experience:**
  - *ML Engineer — Saxo Bank (2020–2024):* built a document-classification service (NLP) cutting
    manual triage ~60%; stood up the MLflow model registry + retraining CI.
  - *Data Scientist — KMD (2017–2020):* demand-forecasting models for a municipal logistics client.
- **Availability:** from 1 September 2026 · **Day rate:** DKK 1,100

---

## The data contract (what the templates must accept)

So we can templatise your filled examples, keep each of these as a **separate, clearly-marked text
node / element** (don't merge two fields into one string, don't bake any into an image or CSS):

**Proposal slots:** `house.name`, `house.tagline`, `house.signatory`, `house.contact`,
`house.website`, `house.logo`; `project.title`, `recipient`, `date`, `validity_line`;
`body.understanding`, `body.approach`, `body.next_steps`, `why_house` (verbatim prose blocks);
**per team member** `consultant.name`, `consultant.title_years`, `consultant.bio` (one block each);
**per proof item** `case.title`, `case.client_display` (already anonymised), `case.outcome`,
`case.delivered_by`; **per pricing row** `line.name`, `line.role`, `line.sell_rate`,
`line.availability`. Running footer: `page X of Y`, `house.name`.

**One-pager slots (per consultant):** `name`, `title`, `seniority`, `location`, `languages`,
`skills[]`, `experience[]` (each: role/employer/dates + the achievement text), `certifications[]`,
`clearance`, `available_from`, `sell_rate`. **Never** a slot for cost rate, margin, engagement type,
or any internal field.

## How we'll verify & integrate (design with this in mind)

We will: swap your concrete strings for the slots above; fill them from real records; run a
fabrication check on the resulting text; and convert to PDF with WeasyPrint. So please: keep facts as
**plain selectable text** (not images), use **one container per section** with a stable
`class`/`id`, ensure it renders correctly as **A4 PDF with working page numbers and page breaks**, and
keep the whole thing **self-contained and offline** (inline `<style>`, no external requests).

**Deliverables recap:** `proposal.html` + `one-pager.html` (each self-contained, brand via `:root`
custom properties, rendering the example above, DRAFT-marked, WeasyPrint/A4/PDF-UA-friendly), each
followed by its **slot → field mapping table**. A one-paragraph note of any WeasyPrint caveats is
welcome.
