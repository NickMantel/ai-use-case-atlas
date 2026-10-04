"""AI tasks. Each returns validated, structured output. Nothing here writes
agreed values: suggestions are stored separately and a person accepts or
overrides them in the UI."""
from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, ValidationError

from ..catalog import CatalogAdapter
from ..config import Framework
from ..models import UseCase, utcnow
from ..providers import LLMError, LLMProvider
from . import catalog_evidence, prompts
from .ai_schemas import ExtractionResult, Mockup, ScoreSuggestion, SizingSuggestion, StarterSQL, StoryDraft, canvas_model

log = logging.getLogger(__name__)


class AIUnavailable(RuntimeError):
    pass


def _run(provider: LLMProvider, task: str, model: type[BaseModel], system: str, prompt: str, hints: dict[str, Any]) -> BaseModel:
    schema = model.model_json_schema()
    last_err: Exception | None = None
    for attempt in (1, 2):
        try:
            raw = provider.generate(task, system, prompt, schema, hints=hints)
            return model.model_validate(raw)
        except ValidationError as exc:
            last_err = exc
            prompt = prompt + f"\n\nYour previous answer failed validation: {exc.errors()[:3]}. Return a corrected result."
            log.warning("AI task %s failed validation (attempt %s)", task, attempt)
        except LLMError as exc:
            raise AIUnavailable(str(exc)) from exc
        except Exception as exc:  # provider SDK errors: network, auth, rate limit
            raise AIUnavailable(f"{type(exc).__name__}: {exc}") from exc
    raise AIUnavailable(f"Model output did not validate: {last_err}")


def _meta(provider: LLMProvider) -> dict[str, Any]:
    return {"provider": provider.describe(), "stub": provider.is_stub, "at": utcnow().isoformat(timespec="seconds")}


def extract_from_notes(provider: LLMProvider, fw: Framework, notes: str, context: str = "") -> dict[str, Any]:
    system, prompt = prompts.extraction(fw, notes, context)
    result = _run(provider, "extract", ExtractionResult, system, prompt, {"fw": fw, "notes": notes})
    valid_keys = {q["key"] for q in fw.workshop_questions}
    out = result.model_dump()
    for item in out["use_cases"]:
        item["answers"] = {a["question_key"]: a["answer"] for a in item["answers"] if a["question_key"] in valid_keys}
    return {**out, "meta": _meta(provider)}


def draft_story(provider: LLMProvider, fw: Framework, uc: UseCase) -> dict[str, Any]:
    system, prompt = prompts.story(fw, uc)
    result = _run(provider, "story", StoryDraft, system, prompt, {"fw": fw, "use_case": uc})
    return {**result.model_dump(), "meta": _meta(provider)}


def suggest_scores(provider: LLMProvider, fw: Framework, uc: UseCase) -> dict[str, Any]:
    system, prompt = prompts.scoring(fw, uc)
    result = _run(provider, "score", ScoreSuggestion, system, prompt, {"fw": fw, "use_case": uc})
    data = result.model_dump()
    return {"lenses": {k: data[k] for k in fw.lens_keys if k in data}, "summary": data["summary"], "meta": _meta(provider)}


def suggest_sizing(provider: LLMProvider, catalog: CatalogAdapter, fw: Framework, uc: UseCase) -> tuple[dict[str, Any], dict[str, Any]]:
    """Returns (sizing_suggestion, catalog_evidence)."""
    system, prompt = prompts.sizing(fw, uc)
    result = _run(provider, "size", SizingSuggestion, system, prompt, {"fw": fw, "use_case": uc}).model_dump()
    evidence = catalog_evidence.gather(catalog, result["data_needs"])
    effort = evidence["effort_from_catalog"] or result["effort_level"]
    basis = "catalogue coverage" if evidence["effort_from_catalog"] else "model read (catalogue not available)"
    suggestion = {
        **result,
        "suggested_scope": result["scope_level"],
        "suggested_effort": effort,
        "effort_basis": basis,
        "suggested_size": fw.size_for(result["scope_level"], effort),
        "meta": _meta(provider),
    }
    return suggestion, evidence


def draft_canvas(provider: LLMProvider, fw: Framework, uc: UseCase) -> dict[str, str]:
    keys = [s["key"] for s in fw.canvas_sections]
    system, prompt = prompts.canvas(fw, uc)
    result = _run(provider, "canvas", canvas_model(keys), system, prompt, {"fw": fw, "use_case": uc})
    return {k: getattr(result, k) for k in keys}


def evidence_tables(uc: UseCase, limit: int = 8) -> list[dict[str, Any]]:
    seen, out = set(), []
    for need in (uc.catalog_evidence or {}).get("needs", []):
        for m in need.get("matches", []):
            if m["full_name"] not in seen:
                seen.add(m["full_name"])
                out.append({"full_name": m["full_name"], "description": m.get("description", ""), "layer": m.get("layer"),
                            "columns": m.get("columns", [])[:40]})
    return out[:limit]


def draft_sql(provider: LLMProvider, catalog: CatalogAdapter, fw: Framework, uc: UseCase) -> dict[str, Any]:
    tables = evidence_tables(uc)
    system, prompt = prompts.starter_sql(fw, uc, catalog.dialect, tables)
    result = _run(provider, "sql", StarterSQL, system, prompt, {"fw": fw, "use_case": uc, "tables": tables})
    return result.model_dump()


def draft_mockup(provider: LLMProvider, fw: Framework, uc: UseCase) -> dict[str, Any]:
    system, prompt = prompts.mockup(fw, uc)
    result = _run(provider, "mockup", Mockup, system, prompt, {"fw": fw, "use_case": uc})
    return result.model_dump()
