"""Prompt builders. Framework content (questions, lenses, sizing bands, canvas
guidance) is injected from YAML so prompts follow client tailoring."""
from __future__ import annotations

import json
from typing import Any

from ..config import Framework
from ..models import UseCase

BASE_SYSTEM = """You support a data and AI advisory team running use case discovery with a client.
Work only from the information provided. Where something is not stated, say it is unknown rather than inventing it.
Write in Australian English, plainly, for business stakeholders. Never use em dashes.
Use cases cover BI and reporting, analytics and ML, generative AI and agentic AI. Some ideas are better solved
by a process or system change; label those honestly rather than forcing a data solution."""


def _options(fw: Framework) -> str:
    sol = ", ".join(f"{s['key']} ({s['label']})" for s in fw.raw["solution_types"])
    return f"Allowed solution_type keys: {sol}\nAllowed domains: {', '.join(fw.raw['domains'])}"


def _questions(fw: Framework) -> str:
    lines = []
    for section in fw.raw["workshop"]["sections"]:
        lines.append(f"{section['title']}:")
        lines += [f"  - [{q['key']}] {q['text']}" for q in section["questions"]]
    return "\n".join(lines)


def use_case_brief(fw: Framework, uc: UseCase) -> str:
    qmap = {q["key"]: q["text"] for q in fw.workshop_questions}
    answers = "\n".join(
        f"- {qmap.get(k, k)}: {v}" for k, v in (uc.workshop_answers or {}).items() if v and str(v).strip()
    ) or "- (none captured)"
    sol = {s["key"]: s["label"] for s in fw.raw["solution_types"]}.get(uc.solution_type or "", "unspecified")
    parts = [
        f"Reference: {uc.ref}",
        f"Title: {uc.title}",
        f"Domain: {uc.domain or 'unspecified'}",
        f"Solution type: {sol}",
        f"Story: {uc.story or '(not yet written)'}",
        f"Gap statement: {uc.gap_statement or '(not yet written)'}",
        f"Use case lead: {uc.use_case_lead or 'unknown'}; sponsor: {uc.sponsor or 'unknown'}",
        f"Workshop answers:\n{answers}",
    ]
    if uc.size:
        size = fw.size_by_key.get(uc.size, {})
        parts.append(f"Agreed size: {size.get('label')} ({size.get('weeks')}); rationale: {uc.sizing_rationale or 'n/a'}")
    if uc.scores:
        parts.append("Agreed DFV ratings: " + ", ".join(f"{k}={v}" for k, v in uc.scores.items()))
    if uc.catalog_evidence and uc.catalog_evidence.get("needs"):
        ev = []
        for need in uc.catalog_evidence["needs"]:
            hits = ", ".join(h["full_name"] for h in need.get("matches", [])[:3]) or "no catalogue match"
            ev.append(f"  - {need['entity']}: {need.get('coverage', 'unknown')} ({hits})")
        parts.append("Catalogue evidence:\n" + "\n".join(ev))
    return "\n".join(parts)


def extraction(fw: Framework, notes: str, context: str) -> tuple[str, str]:
    system = BASE_SYSTEM + "\n\nYour job: turn raw workshop notes into candidate use cases for facilitator review."
    prompt = f"""Workshop principle: {fw.raw['workshop']['principle']}

Workshop questions (use these keys for answers):
{_questions(fw)}

Story format: {fw.raw['workshop']['story']['template']}
Example: {fw.raw['workshop']['story']['example']}

{_options(fw)}

Rules:
- One use case per distinct gap between today and the ideal world. Merge duplicates.
- Each must name a specific role. If no role is identifiable, list the idea under unclear_items instead.
- Only fill workshop answers the notes actually support. Leave the rest out.
- Evidence snippets must be verbatim from the notes and under 25 words each.

Session context: {context or 'none given'}

Workshop notes:
<notes>
{notes}
</notes>"""
    return system, prompt


def story(fw: Framework, uc: UseCase) -> tuple[str, str]:
    system = BASE_SYSTEM + "\n\nYour job: sharpen a captured use case into a crisp story and gap statement."
    prompt = f"""Story format: {fw.raw['workshop']['story']['template']}
Example: {fw.raw['workshop']['story']['example']}
Principle: {fw.raw['workshop']['principle']}

{_options(fw)}

Keep the stakeholder's intent. Make the role specific, the need concrete and the outcome measurable where the
input allows. Suggest up to three follow-up questions that would most improve sizing or scoring.

Captured so far:
{use_case_brief(fw, uc)}"""
    return system, prompt


def scoring(fw: Framework, uc: UseCase) -> tuple[str, str]:
    lenses = "\n".join(
        f"- {lens['key']} ({lens['label']}: {lens['summary']})\n" + "\n".join(f"    * {q}" for q in lens["questions"])
        for lens in fw.lenses
    )
    levels = ", ".join(f"{lvl['key']}={lvl['label']}" for lvl in fw.levels)
    system = BASE_SYSTEM + "\n\nYour job: propose desirability, feasibility and viability ratings for human review."
    prompt = f"""Rate each lens {levels}. Answer each guiding question briefly, in order.
Be conservative: if evidence is thin, rate Medium at most and set confidence low, listing what is missing.
Feasibility must reflect catalogue evidence and agreed size when present.

Lenses:
{lenses}

Use case:
{use_case_brief(fw, uc)}"""
    return system, prompt


def sizing(fw: Framework, uc: UseCase) -> tuple[str, str]:
    sz = fw.raw["sizing"]
    rows = "\n".join(f"  {lvl['key']} {lvl['label']}: {lvl['description']}" for lvl in sz["rows"]["levels"])
    cols = "\n".join(f"  {lvl['key']} {lvl['label']}: {lvl['description']}" for lvl in sz["columns"]["levels"])
    system = BASE_SYSTEM + "\n\nYour job: propose a size and effort read, and list the data the use case needs so it can be checked against the data catalogue."
    prompt = f"""Rows, {sz['rows']['title']}:
{rows}
Columns, {sz['columns']['title']}:
{cols}

List each distinct data need with search terms likely to match table or column names in a lakehouse
(for example 'enrol', 'unit', 'timetable'). Your effort level is provisional: catalogue evidence will be applied after.

Use case:
{use_case_brief(fw, uc)}"""
    return system, prompt


def canvas(fw: Framework, uc: UseCase) -> tuple[str, str]:
    sections = "\n".join(f"- {s['key']} ({s['title']}): {s['guidance']}" for s in fw.canvas_sections)
    system = BASE_SYSTEM + "\n\nYour job: draft a Lean Canvas for a data, analytics or AI use case."
    prompt = f"""Fill every section with 2-5 short lines, each starting with '- '.
Ground everything in the use case. Where information is missing, write a line starting '- TBC:' that says what to confirm.
Use catalogue table names in Required Data and Data Foundations where evidence exists.

Sections:
{sections}

Use case:
{use_case_brief(fw, uc)}"""
    return system, prompt


def starter_sql(fw: Framework, uc: UseCase, dialect: str, tables: list[dict[str, Any]]) -> tuple[str, str]:
    system = BASE_SYSTEM + "\n\nYour job: write a starter query an engineer can run to test feasibility. Read-only, no DDL or DML."
    prompt = f"""Dialect: {dialect}
Only use tables and columns listed below. If they are insufficient, write the best partial query and list assumptions.

Available tables (from the data catalogue):
{json.dumps(tables, indent=1)[:12000]}

Use case:
{use_case_brief(fw, uc)}"""
    return system, prompt


def mockup(fw: Framework, uc: UseCase) -> tuple[str, str]:
    c = fw.raw["brand"]["colours"]
    system = BASE_SYSTEM + "\n\nYour job: produce a low-fidelity UI mock-up of the output the named role would use."
    prompt = f"""Produce one self-contained HTML document (inline CSS only, no JavaScript, no external images or fonts)
showing what the named role would see: for a dashboard, the key tiles, one or two simple CSS/SVG charts with
plausible illustrative numbers clearly labelled 'Illustrative'; for an alert or agent, the message or conversation.
Max width 1000px. Colours: ink {c['ink']}, accent {c['accent']}, blue {c['blue']}, surface {c['surface']}.

Use case:
{use_case_brief(fw, uc)}"""
    return system, prompt
