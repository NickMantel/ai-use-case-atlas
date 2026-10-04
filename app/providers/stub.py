"""Offline stub. Deterministic heuristics so the app is fully usable for demos,
tests and environments where model access is not yet approved. Every output is
labelled so nobody mistakes it for a model's judgement."""
from __future__ import annotations

import re
from typing import Any

from .base import LLMProvider

TAG = "[Offline stub]"

ROLE_RE = re.compile(
    r"\b((?:(?!as\b|an?\b|the\b|our\b|for\b)[a-z]+[ -]){0,2}"
    r"(?:planner|manager|officer|analyst|lead|team|adviser|advisor|coordinator|director|academic|"
    r"student|staff|accountant|controller|administrator|convenor|executive|dean|partner))s?\b",
    re.I,
)
DATA_VOCAB = {
    "enrol": ("student enrolments", ["enrol", "enrolment", "unit"]),
    "admission": ("admissions applications", ["admission", "application", "offer"]),
    "timetabl": ("timetable", ["timetable", "class", "session"]),
    "tutor": ("teaching staff allocations", ["tutor", "staff", "allocation", "workload"]),
    "workload": ("academic workload", ["workload", "allocation", "staff"]),
    "attend": ("attendance and engagement", ["attendance", "engagement", "lms"]),
    "lms": ("LMS activity", ["lms", "activity", "engagement"]),
    "grade": ("results and grades", ["grade", "result", "assessment"]),
    "at-risk": ("student risk indicators", ["risk", "progress", "result"]),
    "budget": ("budget", ["budget", "forecast", "cost_centre"]),
    "variance": ("actuals vs budget", ["actual", "budget", "ledger"]),
    "ledger": ("general ledger", ["ledger", "journal", "gl"]),
    "invoice": ("invoices", ["invoice", "supplier", "payable"]),
    "research": ("research grants", ["grant", "research", "project"]),
    "parcel": ("parcel events", ["parcel", "scan", "event"]),
    "deliver": ("deliveries", ["delivery", "route", "depot"]),
    "customer": ("customers", ["customer", "contact", "case"]),
}


def _role(text: str) -> str:
    m = ROLE_RE.search(text)
    return m.group(1).strip().lower() if m else ""


def _words(text: str, n: int) -> str:
    w = re.sub(r"[^\w\s'-]", " ", text).split()
    return " ".join(w[:n])


def _blocks(notes: str) -> list[str]:
    parts = re.split(r"\n\s*\n|\n\s*[-*•]\s+|\n\s*\d+[.)]\s+", "\n" + notes.strip())
    return [p.strip(" -*•\n") for p in parts if len(p.split()) >= 8]


def _data_needs(text: str) -> list[dict[str, Any]]:
    low = text.lower()
    seen, needs = set(), []
    for key, (entity, terms) in DATA_VOCAB.items():
        if key in low and entity not in seen:
            seen.add(entity)
            needs.append({"entity": entity, "purpose": f"{TAG} mentioned in the use case", "search_terms": terms, "likely_source": ""})
    if not needs:
        needs.append({"entity": "core operational data", "purpose": f"{TAG} no specific entity detected", "search_terms": ["fact"], "likely_source": ""})
    return needs[:5]


class StubProvider(LLMProvider):
    name = "stub"
    is_stub = True

    def describe(self) -> str:
        return "offline stub (no model calls)"

    def generate(self, task: str, system: str, prompt: str, schema: dict[str, Any], hints: dict[str, Any] | None = None) -> dict[str, Any]:
        hints = hints or {}
        handler = getattr(self, f"_{task}")
        return handler(hints)

    # --- tasks ---------------------------------------------------------------
    def _extract(self, h: dict) -> dict:
        out, unclear = [], []
        for block in _blocks(h.get("notes", "")):
            role = _role(block)
            if not role:
                unclear.append(f"{TAG} No role identified: '{_words(block, 12)}…'")
                continue
            text = block.rstrip(".")
            out.append({
                "title": _words(text, 6).capitalize(),
                "role": role,
                "need": _words(text, 18).lower(),
                "outcome": "TBC: confirm the decision or outcome this improves",
                "gap_statement": f"{TAG} {text[:240]}",
                "domain": "",
                "solution_type": "genai" if re.search(r"draft|summar|comment|generat", block, re.I) else "analytics" if re.search(r"predict|forecast|risk|alert", block, re.I) else "bi",
                "answers": [{"question_key": "time_lost", "answer": text[:300]}],
                "evidence": [_words(block, 20)],
            })
        return {"use_cases": out, "unclear_items": unclear}

    def _story(self, h: dict) -> dict:
        uc = h["use_case"]
        answers = " ".join(str(v) for v in (uc.workshop_answers or {}).values())
        role = uc.role or _role(answers) or "TBC role"
        return {
            "title": uc.title,
            "role": role,
            "need": uc.need or _words(answers, 14).lower() or "TBC",
            "outcome": uc.outcome or (uc.workshop_answers or {}).get("six_months") or "TBC: the measurable outcome",
            "gap_statement": uc.gap_statement or f"{TAG} Today: {(uc.workshop_answers or {}).get('time_lost', 'TBC')}. Ideal: {(uc.workshop_answers or {}).get('six_months', 'TBC')}.",
            "solution_type": uc.solution_type or "",
            "follow_up_questions": [
                "How often is this decision made, and by how many people?",
                "Which system holds the data today, and who owns it?",
                "What would you measure to know it worked?",
            ],
        }

    def _score(self, h: dict) -> dict:
        uc, fw = h["use_case"], h["fw"]
        text = " ".join([uc.title or "", uc.need or "", uc.outcome or "", uc.gap_statement or "", " ".join(map(str, (uc.workshop_answers or {}).values()))]).lower()
        d = "H" if uc.role and re.search(r"manual|hours|chase|confiden|trust|late|delay|spreadsheet", text) else "M"
        cov = [n.get("coverage") for n in (uc.catalog_evidence or {}).get("needs", [])]
        if cov and all(c == "reuse" for c in cov):
            f = "H"
        elif cov.count("build") > 1 or uc.size == "XL":
            f = "L"
        elif cov or uc.solution_type in ("genai", "agentic") or uc.size in ("L",):
            f = "M"
        else:
            f = "M"
        v = "H" if re.search(r"\$|hours|revenue|cost|compliance|risk|retention|week", text) else "M"
        out = {}
        for lens, level in zip(fw.lens_keys, (d, f, v)):
            questions = next(x["questions"] for x in fw.lenses if x["key"] == lens)
            out[lens] = {
                "level": level,
                "rationale": f"{TAG} Keyword heuristic, not a judgement. Rated {level} from the captured text and catalogue coverage.",
                "question_answers": [f"{TAG} Review manually." for _ in questions],
                "confidence": "low",
                "missing_information": ["Model-based assessment (switch LLM_PROVIDER from stub)"],
            }
        return {**out, "summary": f"{TAG} Heuristic ratings for demo use only."}

    def _size(self, h: dict) -> dict:
        uc = h["use_case"]
        text = " ".join([uc.title or "", uc.need or "", uc.outcome or "", uc.gap_statement or "", " ".join(map(str, (uc.workshop_answers or {}).values()))])
        needs = _data_needs(text)
        agentic = bool(re.search(r"agent|autonom|multi-step|workflow", text, re.I)) or uc.solution_type == "agentic"
        scope = "H" if agentic or len(needs) >= 4 else "M" if len(needs) >= 2 else "L"
        return {
            "outputs": [uc.title or "Primary output"],
            "data_needs": needs,
            "is_multi_step_or_agentic": agentic,
            "scope_level": scope,
            "scope_rationale": f"{TAG} {len(needs)} data need(s) detected{'; agentic pattern' if agentic else ''}.",
            "effort_level": "M",
            "effort_rationale": f"{TAG} Default before catalogue evidence.",
            "risks": ["Stub output: confirm data needs with the use case lead"],
        }

    def _canvas(self, h: dict) -> dict:
        uc, fw = h["use_case"], h["fw"]
        needs = (uc.catalog_evidence or {}).get("needs", [])
        tables = [m["full_name"] for n in needs for m in n.get("matches", [])[:2]]
        sol = {s["key"]: s["label"] for s in fw.raw["solution_types"]}.get(uc.solution_type or "", "TBC")
        content = {
            "business_problem": f"- {uc.gap_statement or 'TBC: gap statement'}",
            "solution_description": f"- {sol} solution for {uc.role or 'TBC role'}\n- TBC: consumption tool and refresh cadence",
            "systems_data_tech": "\n".join(f"- {t}" for t in tables) or "- TBC: source systems",
            "capability_requirements": "- Source analysis\n- Data engineering\n- " + ("Prompt and evaluation design" if uc.solution_type in ("genai", "agentic") else "Data modelling"),
            "business_users": f"- {uc.role or 'TBC'}\n- Sponsor: {uc.sponsor or 'TBC'}",
            "estimated_benefits": f"- {uc.outcome or 'TBC: outcome'}",
            "data_foundations": "\n".join(f"- Reusable {n['entity']} dataset" for n in needs) or "- TBC",
            "required_data": "\n".join(f"- {n['entity']} ({n.get('coverage', 'unchecked')})" for n in needs) or "- TBC: run sizing to check the catalogue",
            "assumptions_risks": f"- {TAG} Generated without a model; review every line\n- TBC: data quality and access approvals",
            "estimated_resources": f"- Data engineer\n- Analyst\n- SME: {uc.use_case_lead or 'TBC'}",
        }
        return {s["key"]: content.get(s["key"], "- TBC") for s in fw.canvas_sections}

    def _sql(self, h: dict) -> dict:
        tables = h.get("tables") or []
        if not tables:
            return {"sql": "-- No catalogue tables matched. Run sizing first.", "explanation": TAG, "assumptions": [], "tables_used": []}
        t = tables[0]
        cols = [c["name"] for c in t.get("columns", [])][:6] or ["*"]
        col_list = ",\n  ".join(cols)
        sql = f"SELECT\n  {col_list}\nFROM {t['full_name']}\nLIMIT 100"
        return {"sql": sql, "explanation": f"{TAG} Profiles the best-matching table.", "assumptions": ["Columns chosen by position, not meaning"], "tables_used": [t["full_name"]]}

    def _mockup(self, h: dict) -> dict:
        uc, fw = h["use_case"], h["fw"]
        c = fw.raw["brand"]["colours"]
        tiles = "".join(
            f"<div style='flex:1;background:#fff;border:1px solid {c['border']};border-radius:10px;padding:14px'>"
            f"<div style='font-size:12px;color:#5b6b80'>Metric {i}</div><div style='font-size:26px;font-weight:700;color:{c['ink']}'>—</div></div>"
            for i in (1, 2, 3)
        )
        html = (
            f"<!doctype html><html><body style='margin:0;font-family:system-ui;background:{c['surface']};padding:20px'>"
            f"<div style='max-width:960px;margin:auto'><div style='color:{c['accent']};font-size:12px;font-weight:700'>ILLUSTRATIVE {TAG}</div>"
            f"<h1 style='color:{c['ink']};font-size:22px'>{uc.title}</h1><p style='color:#44546a'>For: {uc.role or 'TBC'}</p>"
            f"<div style='display:flex;gap:12px'>{tiles}</div>"
            f"<div style='margin-top:14px;height:220px;background:#fff;border:1px dashed {c['blue']};border-radius:10px;display:flex;align-items:center;justify-content:center;color:{c['blue']}'>Primary chart</div>"
            "</div></body></html>"
        )
        return {"html": html, "description": f"{TAG} Placeholder layout."}
