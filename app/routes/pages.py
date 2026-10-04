from __future__ import annotations

from collections import Counter

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_framework
from ..db import get_db
from ..models import Event, IntakeRound, UseCase
from ..services.ranking import rank
from ..web import NAME_COOKIE, redirect, render

router = APIRouter()


def _all(db: Session) -> list[UseCase]:
    return list(db.scalars(select(UseCase)))


@router.get("/")
def dashboard(request: Request, db: Session = Depends(get_db)):
    fw = get_framework()
    ucs = _all(db)
    by_status = Counter(uc.status for uc in ucs)
    stages = []
    for stage in fw.raw["workflow"]["stages"]:
        stages.append({**stage, "count": sum(by_status.get(s, 0) for s in stage["statuses"]),
                       "breakdown": [(fw.status_labels[s], by_status.get(s, 0)) for s in stage["statuses"]]})
    off_flow = [(fw.status_labels[s], by_status.get(s, 0)) for s in ("parked", "rejected", "merged") if s in fw.status_labels]
    ranked = [r for r in rank(fw, [u for u in ucs if u.status not in ("parked", "rejected", "merged")]) if r.score is not None][:5]
    attention = [uc for uc in ucs if uc.status in ("captured", "in_review")]
    events = list(db.scalars(select(Event).order_by(Event.at.desc()).limit(12)))
    rounds = list(db.scalars(select(IntakeRound).order_by(IntakeRound.created_at.desc()).limit(5)))
    return render(request, "dashboard.html", stages=stages, off_flow=off_flow, ranked=ranked, attention=attention,
                  events=events, rounds=rounds, total=len(ucs))


@router.get("/backlog")
def backlog(request: Request, stage: str = "", domain: str = "", size: str = "", q: str = "", show_closed: int = 0,
            db: Session = Depends(get_db)):
    fw = get_framework()
    ucs = _all(db)
    if not show_closed:
        ucs = [u for u in ucs if u.status not in ("parked", "rejected", "merged")]
    if stage:
        st = next((s for s in fw.raw["workflow"]["stages"] if s["key"] == stage), None)
        if st:
            ucs = [u for u in ucs if u.status in st["statuses"]]
    if domain:
        ucs = [u for u in ucs if u.domain == domain]
    if size:
        ucs = [u for u in ucs if u.size == size]
    if q:
        ql = q.lower()
        ucs = [u for u in ucs if ql in f"{u.ref} {u.title} {u.story} {u.gap_statement or ''} {u.use_case_lead or ''}".lower()]
    ranked = rank(fw, ucs)
    domains = sorted({u.domain for u in _all(db) if u.domain})
    return render(request, "backlog.html", ranked=ranked, filters={"stage": stage, "domain": domain, "size": size, "q": q, "show_closed": show_closed},
                  domains=domains)


@router.get("/portfolio")
def portfolio(request: Request, db: Session = Depends(get_db)):
    fw = get_framework()
    active = [u for u in _all(db) if u.status not in ("parked", "rejected", "merged")]
    ranked = rank(fw, active)
    cells: dict[tuple[str, str], list[UseCase]] = {}
    for u in active:
        if u.scope_level and u.effort_level:
            cells.setdefault((u.scope_level, u.effort_level), []).append(u)
    # value vs effort plot: value = mean of desirability + viability points; effort = size order
    pts, size_order = fw.level_points, {s["key"]: s["order"] for s in fw.sizes}
    plot = []
    for item in ranked:
        u = item.use_case
        if item.score is None or not u.size:
            continue
        value = (pts.get(u.scores.get("desirability"), 0) + pts.get(u.scores.get("viability"), 0)) / 2
        plot.append({"uc": u, "value": value, "effort": size_order.get(u.size, 3), "feas": u.scores.get("feasibility"), "rank": item.computed_rank})
    slots: Counter = Counter()
    for p in plot:  # fan out points that share a position so labels stay readable
        key = (p["effort"], p["value"])
        p["slot"] = slots[key]
        slots[key] += 1
    return render(request, "portfolio.html", ranked=ranked, cells=cells, plot=plot)


@router.get("/framework")
def framework_page(request: Request):
    return render(request, "framework.html")


@router.post("/whoami")
def set_name(request: Request, name: str = Form(...), next: str = Form("/")):
    resp = redirect(next if next.startswith("/") else "/", msg=f"Recording changes as {name.strip()[:80]}")
    resp.set_cookie(NAME_COOKIE, name.strip()[:80], max_age=60 * 60 * 24 * 180, httponly=True, samesite="lax")
    return resp
