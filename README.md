# AI Use Case Atlas

A portfolio management tool for capturing, assessing and prioritising data, analytics and AI use cases across an organisation. It runs the full intake cycle: workshop capture, qualification, catalogue-informed sizing, desirability/feasibility/viability (DFV) scoring, a Lean Canvas per use case, and a ranked backlog ready for portfolio review.

It is built to be reused across clients. The method (questions, lenses, sizing matrix, canvas, workflow owners) lives in YAML, the model route and data catalogue are swappable adapters, and the app is one container that runs on GCP, Azure or Databricks.

## What it does

| Stage | In the tool | AI assistance (always reviewed by a person) |
|---|---|---|
| 1. Ideation | Workshops as intake rounds. Guided capture using the Today / Ideal world questions and the "As a…, I need…, so that…" story. | Turns pasted notes or transcripts into candidate use cases; sharpens stories and gap statements; suggests follow-up questions. |
| Qualification | Checklist, outcome (qualified / parked / not progressing / merged) and a required note for anything not qualified. | None. This is a human gate. |
| 2. Sizing | 3x3 scope vs effort matrix producing XS to XL with indicative weeks. | Lists the data a use case needs, searches the data catalogue (Unity Catalog, BigQuery or a demo catalogue) and classes each need as reuse / develop / build to suggest the effort column. |
| 3. Prioritisation and scoring | High / Medium / Low per lens with discussion notes; deterministic, explainable ranking; agreed rank override from portfolio review. | Proposes a rating per lens with rationale, answers to each guiding question, confidence and missing information. |
| 4. Governance and sequencing | Approved for delivery backlog status; portfolio pack export. | None. |
| Lean Canvas | Ten-section canvas per use case, editable in place, exported to PowerPoint in the template layout. | Drafts every section from the story, answers, size, scores and catalogue evidence, marking unknowns as "TBC". |
| Accelerators | Starter SQL and a UI mock-up per use case. | Generates a read-only query grounded in catalogue tables (never executed) and a sandboxed HTML mock-up. |

Every change, AI suggestion and override is written to an audit trail. AI suggestions are stored separately from agreed values.

Exports: backlog (Excel, CSV), portfolio pack (PowerPoint: ranked DFV table, sizing matrix with use cases placed, one Lean Canvas per use case), single canvas (PowerPoint or print to PDF), and read-only JSON at `/api/usecases`.

## Quick start (laptop)

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
cp .env.example .env            # optional; defaults work offline
.venv/bin/python -m uvicorn app.main:app --reload --port 8000
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m uvicorn app.main:app --reload --port 8000
```

Open http://localhost:8000. With the defaults it runs fully offline: `LLM_PROVIDER=stub` uses labelled keyword heuristics instead of a model, `CATALOG_ADAPTER=demo` uses a synthetic university catalogue, and illustrative data from the worked example is loaded into an empty database.

To use Claude via the Anthropic API:

```bash
export LLM_PROVIDER=anthropic ANTHROPIC_API_KEY=... LLM_MODEL=<current model id>
```

Run the tests with `make test` (27 tests: ranking, sizing rules, the full lifecycle through the web UI, exports, provider plumbing and catalogue adapters against fake SDK clients).

## Configuration

| Variable | Values | Notes |
|---|---|---|
| `FRAMEWORK` | `default`, `deakin`, `auspost`, or any `frameworks/<name>.yaml` | Client overlay deep-merged over `frameworks/default.yaml`. |
| `DATABASE_URL` | SQLite (default) or `postgresql+psycopg://…` | Use Postgres for any shared deployment (container file systems are ephemeral). |
| `LLM_PROVIDER` | `stub`, `anthropic`, `vertex`, `databricks`, `openai_compatible` | See `.env.example` for each route's settings. |
| `LLM_MODEL` | model ID or serving endpoint name | Required for every route except `stub`. |
| `CATALOG_ADAPTER` | `demo`, `unity_catalog`, `bigquery`, `none` | Metadata only; table contents are never read. |
| `SEED_DEMO_DATA` | `true` / `false` | Loads illustrative data into an empty database only. |

### Tailoring the method for a client

Copy `frameworks/deakin.yaml` to `frameworks/<client>.yaml` and change only what differs: brand and colours, domains, lens questions and weights, workflow owners and cadence, qualification checks, sizing bands, Lean Canvas sections. Set `FRAMEWORK=<client>`. No code changes or migrations are needed; use case fields that depend on the framework are stored as JSON.

### Identity

Behind a platform front door the app reads the signed-in user from the proxy header (Databricks Apps `X-Forwarded-Email`, Google IAP, Azure Easy Auth). Otherwise users set a display name, stored in a cookie, which is recorded against their changes. There is no in-app authentication: deploy it behind the platform's SSO. See `docs/deployment.md`.

## Architecture

```
app/
  main.py               FastAPI app, startup (create tables, seed)
  config.py             env settings and framework YAML loading/merging
  models.py             IntakeRound, UseCase, Event (audit trail)
  routes/               pages, workshops, use case lifecycle, exports, JSON API
  services/
    ranking.py          deterministic DFV ranking and flags
    usecases.py         lifecycle operations; every mutation logs an Event
    catalog_evidence.py reuse / develop / build classification and effort rule
    ai.py, prompts.py   AI tasks with pydantic-validated structured output, one retry
    exports.py          PowerPoint and Excel
  providers/            stub, Anthropic (API + Vertex), OpenAI-compatible (+ Databricks SDK auth)
  catalog/              demo, Unity Catalog, BigQuery adapters
  templates/, static/   server-rendered HTML, one CSS file, htmx vendored (no build step, no CDN)
frameworks/             default.yaml plus client overlays
```

Design choices:

- **Server-rendered, no build step, no external assets.** Works in locked-down client networks and is easy to hand over.
- **Structured output everywhere.** Each AI task has a pydantic schema enforced through a forced tool call; invalid output is retried once, then surfaced as an error.
- **People decide.** The model never writes agreed values. Suggestions sit beside the form; overrides are logged.
- **Model-generated HTML is sandboxed.** Mock-ups are served with a `sandbox` CSP and rendered in a sandboxed iframe with no scripts or network.
- **Generated SQL is never executed.** Catalogue queries are metadata only and fully parameterised.

## Status and known limits

- The Unity Catalog and BigQuery adapters are written against the documented SDKs and `INFORMATION_SCHEMA` views and are tested with fake clients. They have not yet been run against a live workspace or project; validate in a sandbox first.
- The Anthropic, Vertex, Databricks and OpenAI-compatible routes are tested with fake clients only. Prompt quality has not yet been evaluated against real workshop material.
- Schema changes use `create_all`; add Alembic before the first breaking model change in a shared deployment.
- No in-app roles yet: anyone who can reach the app can edit. Restrict access at the platform.
- No CSRF tokens on forms. Acceptable behind platform SSO on an internal network; add before any wider exposure.
- Roadmap and sequencing views are out of scope for this version.

See `PROVENANCE.md` for how this code base was produced.
