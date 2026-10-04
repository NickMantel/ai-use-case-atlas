"""Use case lifecycle operations. Every mutation records an Event."""
from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import Framework
from ..models import Event, UseCase, utcnow
from .ranking import priority_score

# Statuses that mean "this has left the main flow".
TERMINAL_OUTCOMES = {"parked", "rejected", "merged"}


def next_ref(db: Session) -> str:
    n = db.scalar(select(func.count(UseCase.id))) or 0
    while True:
        n += 1
        ref = f"UC-{n:03d}"
        if not db.scalar(select(UseCase.id).where(UseCase.ref == ref)):
            return ref


def record(db: Session, uc: UseCase, actor: str, kind: str, summary: str, **detail: Any) -> None:
    db.add(Event(use_case=uc, actor=actor or "unknown", kind=kind, summary=summary, detail=detail))


def create_use_case(db: Session, actor: str, **fields: Any) -> UseCase:
    uc = UseCase(ref=next_ref(db), created_by=actor, **fields)
    if not uc.title:
        uc.title = (uc.need or "Untitled use case")[:120]
    db.add(uc)
    db.flush()
    record(db, uc, actor, "created", f"Captured {uc.ref}: {uc.title}")
    return uc


EDITABLE_FIELDS = (
    "title", "domain", "use_case_lead", "sponsor", "solution_type", "role", "need", "outcome",
    "gap_statement", "intake_round_id",
)


def update_fields(db: Session, uc: UseCase, actor: str, values: dict[str, Any], answers: dict[str, str] | None = None) -> list[str]:
    changed = []
    for name in EDITABLE_FIELDS:
        if name in values:
            new = values[name] if values[name] not in ("",) else None
            if name == "title" and not new:
                continue  # title is required; ignore a blanked field
            if getattr(uc, name) != new:
                changed.append(name)
                setattr(uc, name, new)
    if answers is not None:
        merged = {**(uc.workshop_answers or {}), **{k: v for k, v in answers.items()}}
        if merged != (uc.workshop_answers or {}):
            uc.workshop_answers = merged
            changed.append("workshop_answers")
    if changed:
        record(db, uc, actor, "edited", f"Edited {', '.join(changed)}", fields=changed)
    return changed


def set_status(db: Session, fw: Framework, uc: UseCase, actor: str, status: str, comment: str = "") -> None:
    if status not in fw.status_labels:
        raise ValueError(f"Unknown status {status}")
    if status == uc.status:
        return
    old = uc.status
    uc.status = status
    summary = f"Status {fw.status_labels.get(old, old)} → {fw.status_labels[status]}"
    if comment:
        summary += f": {comment}"
    record(db, uc, actor, "status", summary, old=old, new=status, comment=comment)


def qualify(db: Session, fw: Framework, uc: UseCase, actor: str, checks: dict[str, bool], outcome: str, note: str, merged_into: str | None) -> None:
    uc.qualification_checks = checks
    uc.qualification_outcome = outcome
    uc.qualification_note = note or None
    uc.merged_into_ref = merged_into if outcome == "merged" else None
    passed = sum(1 for v in checks.values() if v)
    record(db, uc, actor, "qualified", f"Qualification: {outcome} ({passed}/{len(checks)} checks)", checks=checks, note=note)
    set_status(db, fw, uc, actor, outcome, note)


def apply_sizing(db: Session, fw: Framework, uc: UseCase, actor: str, scope: str, effort: str, rationale: str, source: str = "human") -> None:
    size = fw.size_for(scope, effort)
    if size is None:
        raise ValueError("Scope and effort must both be set")
    old = uc.size
    uc.scope_level, uc.effort_level, uc.size = scope, effort, size
    uc.sizing_rationale = rationale or uc.sizing_rationale
    label = fw.size_by_key[size]["label"]
    record(db, uc, actor, "sized", f"Sized {label} (scope {scope}, effort {effort}){' from AI suggestion' if source == 'ai' else ''}",
           old=old, new=size, scope=scope, effort=effort, source=source)
    if uc.status in ("qualified", "captured", "in_review"):
        set_status(db, fw, uc, actor, "sized")


def apply_scores(db: Session, fw: Framework, uc: UseCase, actor: str, scores: dict[str, str], notes: dict[str, str], source: str = "human") -> None:
    old = dict(uc.scores or {})
    uc.scores = {k: v for k, v in scores.items() if k in fw.lens_keys and v in fw.level_points}
    uc.score_notes = {**(uc.score_notes or {}), **notes}
    uc.priority_score = priority_score(fw, uc.scores)
    overrides = []
    suggested = (uc.score_suggestion or {}).get("lenses", {})
    for k, v in uc.scores.items():
        s = suggested.get(k, {}).get("level")
        if s and s != v:
            overrides.append(f"{k} {s}→{v}")
    summary = "Scored " + ", ".join(f"{k[0].upper()}={v}" for k, v in uc.scores.items())
    if overrides:
        summary += f" (overrode AI: {', '.join(overrides)})"
    record(db, uc, actor, "scored", summary, old=old, new=uc.scores, source=source, overrides=overrides)
    if uc.priority_score is not None and uc.status in ("qualified", "sized", "captured", "in_review"):
        set_status(db, fw, uc, actor, "scored")


def set_agreed_rank(db: Session, uc: UseCase, actor: str, rank: int | None) -> None:
    old = uc.agreed_rank
    uc.agreed_rank = rank
    record(db, uc, actor, "rank", f"Agreed rank {old or '-'} → {rank or 'cleared'}", old=old, new=rank)


def save_canvas(db: Session, uc: UseCase, actor: str, canvas: dict[str, str], generated: bool = False) -> None:
    uc.canvas = canvas
    if generated:
        uc.canvas_generated_at = utcnow()
    record(db, uc, actor, "canvas", "Lean Canvas generated" if generated else "Lean Canvas edited")
