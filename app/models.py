"""Relational model. Kept deliberately small: one row per use case, JSON for
framework-driven fields (so a client can change questions or canvas sections
without a schema migration), and an append-only event log for the audit trail."""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import JSON, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def article(word: str | None) -> str:
    """'an' before a vowel sound (approximate), else 'a'."""
    w = (word or "").strip().lower()
    return "an" if w[:1] in ("a", "e", "i", "o") or w.startswith(("hon", "hour")) else "a"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class IntakeRound(Base):
    """A workshop or intake round that use cases are captured in."""

    __tablename__ = "intake_rounds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    held_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    domain: Mapped[str | None] = mapped_column(String(120), nullable=True)
    facilitator: Mapped[str | None] = mapped_column(String(200), nullable=True)
    attendees: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    use_cases: Mapped[list[UseCase]] = relationship(back_populates="intake_round")


class UseCase(Base):
    __tablename__ = "use_cases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ref: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(40), default="captured", index=True)
    intake_round_id: Mapped[int | None] = mapped_column(ForeignKey("intake_rounds.id"), nullable=True)
    domain: Mapped[str | None] = mapped_column(String(120), nullable=True)
    use_case_lead: Mapped[str | None] = mapped_column(String(200), nullable=True)
    sponsor: Mapped[str | None] = mapped_column(String(200), nullable=True)
    solution_type: Mapped[str | None] = mapped_column(String(40), nullable=True)

    # Story: "As a {role}, I need {need}, so that {outcome}."
    role: Mapped[str | None] = mapped_column(String(200), nullable=True)
    need: Mapped[str | None] = mapped_column(Text, nullable=True)
    outcome: Mapped[str | None] = mapped_column(Text, nullable=True)
    gap_statement: Mapped[str | None] = mapped_column(Text, nullable=True)
    workshop_answers: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    # Qualification
    qualification_checks: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    qualification_outcome: Mapped[str | None] = mapped_column(String(40), nullable=True)
    qualification_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    merged_into_ref: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Sizing (rows = scope/complexity, columns = build effort/data availability)
    scope_level: Mapped[str | None] = mapped_column(String(2), nullable=True)
    effort_level: Mapped[str | None] = mapped_column(String(2), nullable=True)
    size: Mapped[str | None] = mapped_column(String(4), nullable=True)
    sizing_rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    catalog_evidence: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    sizing_suggestion: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    # Scoring: {"desirability": "H", ...}; notes per lens; AI suggestion kept separately
    scores: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    score_notes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    score_suggestion: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    priority_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    agreed_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Lean Canvas: {section_key: text}
    canvas: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    canvas_generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Accelerators
    starter_sql: Mapped[str | None] = mapped_column(Text, nullable=True)
    mockup_html: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    intake_round: Mapped[IntakeRound | None] = relationship(back_populates="use_cases")
    events: Mapped[list[Event]] = relationship(
        back_populates="use_case", order_by="Event.at.desc()", cascade="all, delete-orphan"
    )

    @property
    def story(self) -> str:
        if not (self.role or self.need or self.outcome):
            return ""
        return f"As {article(self.role)} {self.role or '…'}, I need {self.need or '…'}, so that {self.outcome or '…'}."


class Event(Base):
    """Append-only audit trail: who changed what, when, and why."""

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    use_case_id: Mapped[int] = mapped_column(ForeignKey("use_cases.id", ondelete="CASCADE"), index=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    actor: Mapped[str] = mapped_column(String(200), default="unknown")
    kind: Mapped[str] = mapped_column(String(40))  # created, edited, status, sized, scored, canvas, ai, rank
    summary: Mapped[str] = mapped_column(Text)
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    use_case: Mapped[UseCase] = relationship(back_populates="events")
