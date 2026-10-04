"""Structured outputs for every AI task. Pydantic validates what comes back."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, create_model

Level = Literal["H", "M", "L"]
Confidence = Literal["high", "medium", "low"]


class WorkshopAnswer(BaseModel):
    question_key: str = Field(description="Key of the workshop question this answers")
    answer: str


class ExtractedUseCase(BaseModel):
    title: str = Field(description="Short noun phrase, max 8 words, e.g. 'Teaching demand forecast'")
    role: str = Field(description="The named role who has the problem, e.g. 'faculty workload planner'")
    need: str = Field(description="What they need, phrased to follow 'I need'")
    outcome: str = Field(description="Why, phrased to follow 'so that'")
    gap_statement: str = Field(description="One or two sentences: today vs the ideal world. The gap is the use case.")
    domain: str = Field(default="", description="Best-fit domain from the allowed list, or empty")
    solution_type: str = Field(default="", description="Best-fit solution type key from the allowed list")
    answers: list[WorkshopAnswer] = Field(default_factory=list, description="Answers to the workshop questions, only where the notes support them")
    evidence: list[str] = Field(default_factory=list, description="Short verbatim snippets from the notes that support this use case")


class ExtractionResult(BaseModel):
    use_cases: list[ExtractedUseCase]
    unclear_items: list[str] = Field(default_factory=list, description="Ideas in the notes too vague to turn into a use case, with what is missing")


class StoryDraft(BaseModel):
    title: str
    role: str
    need: str
    outcome: str
    gap_statement: str
    solution_type: str = ""
    follow_up_questions: list[str] = Field(default_factory=list, description="Questions the facilitator should ask to sharpen this use case")


class LensAssessment(BaseModel):
    level: Level
    rationale: str = Field(description="Two or three sentences, grounded in the captured information")
    question_answers: list[str] = Field(description="One short answer per guiding question for this lens, in order")
    confidence: Confidence
    missing_information: list[str] = Field(default_factory=list)


class ScoreSuggestion(BaseModel):
    desirability: LensAssessment
    feasibility: LensAssessment
    viability: LensAssessment
    summary: str = Field(description="One sentence overall read")


class DataNeed(BaseModel):
    entity: str = Field(description="Business entity or dataset, e.g. 'unit enrolments'")
    purpose: str = Field(description="Why the use case needs it")
    search_terms: list[str] = Field(description="2-4 lowercase keywords likely to appear in table or column names")
    likely_source: str = Field(default="", description="Likely source system if known")


class SizingSuggestion(BaseModel):
    outputs: list[str] = Field(description="Distinct outputs the solution produces (dashboards, models, alerts, agents)")
    data_needs: list[DataNeed]
    is_multi_step_or_agentic: bool
    scope_level: Level
    scope_rationale: str
    effort_level: Level = Field(description="Your effort read before catalogue evidence is applied")
    effort_rationale: str
    risks: list[str] = Field(default_factory=list)


class StarterSQL(BaseModel):
    sql: str = Field(description="A single read-only SELECT (CTEs allowed) in the stated dialect")
    explanation: str
    assumptions: list[str] = Field(default_factory=list)
    tables_used: list[str] = Field(default_factory=list)


class Mockup(BaseModel):
    html: str = Field(description="One self-contained HTML document with inline CSS only. No scripts, no external resources.")
    description: str


def canvas_model(section_keys: list[str]) -> type[BaseModel]:
    """Lean Canvas sections come from the framework YAML, so build the model at runtime."""
    fields = {k: (str, Field(description=f"Content for the '{k}' section as short bullet lines")) for k in section_keys}
    return create_model("LeanCanvasDraft", **fields)  # type: ignore[call-overload]
