from __future__ import annotations

import csv
import io
from datetime import date

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_framework
from ..db import get_db
from ..models import UseCase
from ..services import exports
from ..services.ranking import rank

router = APIRouter(prefix="/export")
PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _ranked(db: Session, include_closed: bool = False):
    ucs = [u for u in db.scalars(select(UseCase)) if include_closed or u.status not in ("parked", "rejected", "merged")]
    return rank(get_framework(), ucs)


def _file(data: bytes, media: str, name: str) -> Response:
    return Response(data, media_type=media, headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/backlog.xlsx")
def backlog_xlsx(include_closed: int = 1, db: Session = Depends(get_db)):
    return _file(exports.backlog_xlsx(get_framework(), _ranked(db, bool(include_closed))), XLSX, f"use-case-backlog-{date.today()}.xlsx")


@router.get("/backlog.csv")
def backlog_csv(db: Session = Depends(get_db)):
    fw = get_framework()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["rank", "ref", "title", "status", "domain", "story", "gap", "size", *fw.lens_keys, "priority_score", "agreed_rank"])
    for item in _ranked(db, True):
        u = item.use_case
        w.writerow([item.computed_rank, u.ref, u.title, u.status, u.domain, u.story, u.gap_statement, u.size,
                    *[(u.scores or {}).get(k) for k in fw.lens_keys], item.score, u.agreed_rank])
    return _file(buf.getvalue().encode(), "text/csv", f"use-case-backlog-{date.today()}.csv")


@router.get("/portfolio.pptx")
def portfolio_pptx(db: Session = Depends(get_db)):
    fw = get_framework()
    client = fw.raw["brand"].get("client_name") or "Data and AI"
    return _file(exports.portfolio_pptx(fw, _ranked(db), f"{client} use case portfolio"), PPTX, f"use-case-portfolio-{date.today()}.pptx")


@router.get("/canvases.pptx")
def canvases_pptx(db: Session = Depends(get_db)):
    ucs = [i.use_case for i in _ranked(db) if i.use_case.canvas]
    return _file(exports.lean_canvas_pptx(get_framework(), ucs), PPTX, f"lean-canvases-{date.today()}.pptx")
