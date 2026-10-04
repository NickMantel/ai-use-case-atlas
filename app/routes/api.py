"""Read-only JSON for integrations (BI, Confluence/SharePoint embeds, roadmap tooling later)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_framework
from ..db import get_db
from ..models import UseCase
from ..services.ranking import rank

router = APIRouter()


@router.get("/healthz")
def healthz():
    return {"ok": True}


@router.get("/api/usecases")
def list_usecases(db: Session = Depends(get_db)):
    fw = get_framework()
    out = []
    for item in rank(fw, list(db.scalars(select(UseCase)))):
        u = item.use_case
        out.append({
            "ref": u.ref, "title": u.title, "status": u.status, "stage": (fw.stage_for_status(u.status) or {}).get("key"),
            "domain": u.domain, "story": u.story, "gap_statement": u.gap_statement, "solution_type": u.solution_type,
            "use_case_lead": u.use_case_lead, "sponsor": u.sponsor,
            "sizing": {"scope": u.scope_level, "effort": u.effort_level, "size": u.size},
            "scores": u.scores, "priority_score": item.score, "computed_rank": item.computed_rank, "agreed_rank": u.agreed_rank,
            "flags": item.flags, "canvas": u.canvas, "updated_at": u.updated_at.isoformat() if u.updated_at else None,
        })
    return out
