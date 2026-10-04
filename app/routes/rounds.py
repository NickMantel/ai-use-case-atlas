from __future__ import annotations

import json
from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_framework
from ..db import get_db
from ..models import IntakeRound
from ..providers import get_provider
from ..services import ai
from ..services.usecases import create_use_case, record
from ..web import current_user, redirect, render

router = APIRouter(prefix="/rounds")


@router.get("")
def list_rounds(request: Request, db: Session = Depends(get_db)):
    rounds = list(db.scalars(select(IntakeRound).order_by(IntakeRound.created_at.desc())))
    return render(request, "rounds.html", rounds=rounds, today=date.today().isoformat())


@router.post("")
def create_round(request: Request, name: str = Form(...), held_on: str = Form(""), domain: str = Form(""),
                 facilitator: str = Form(""), attendees: str = Form(""), notes: str = Form(""), db: Session = Depends(get_db)):
    rnd = IntakeRound(name=name.strip(), held_on=date.fromisoformat(held_on) if held_on else None, domain=domain or None,
                      facilitator=facilitator or None, attendees=attendees or None, notes=notes or None)
    db.add(rnd)
    db.commit()
    return redirect(f"/rounds/{rnd.id}", msg="Intake round opened")


@router.get("/{round_id}")
def round_detail(round_id: int, request: Request, db: Session = Depends(get_db)):
    rnd = db.get(IntakeRound, round_id)
    if not rnd:
        return redirect("/rounds", err="Round not found")
    return render(request, "round_detail.html", rnd=rnd)


@router.post("/{round_id}/extract")
def extract(round_id: int, request: Request, notes: str = Form(...), db: Session = Depends(get_db)):
    """Turn pasted workshop notes or a transcript into candidate use cases for review."""
    fw = get_framework()
    rnd = db.get(IntakeRound, round_id)
    if not rnd:
        return redirect("/rounds", err="Round not found")
    context = f"{rnd.name}; domain {rnd.domain or 'mixed'}; attendees {rnd.attendees or 'not recorded'}"
    try:
        result = ai.extract_from_notes(get_provider(), fw, notes, context)
    except ai.AIUnavailable as exc:
        return redirect(f"/rounds/{round_id}", err=f"AI extraction failed: {exc}")
    rnd.notes = ((rnd.notes or "") + "\n\n--- notes imported ---\n" + notes).strip()
    db.commit()
    return render(request, "round_extract.html", rnd=rnd, result=result, payload=json.dumps(result["use_cases"]))


@router.post("/{round_id}/accept")
async def accept(round_id: int, request: Request, db: Session = Depends(get_db)):
    fw = get_framework()
    form = await request.form()
    actor, _ = current_user(request)
    candidates = json.loads(form.get("payload", "[]"))
    chosen = {int(i) for i in form.getlist("accept")}
    created = []
    for i, c in enumerate(candidates):
        if i not in chosen:
            continue
        domain = c.get("domain") if c.get("domain") in fw.raw["domains"] else None
        sol = c.get("solution_type") if c.get("solution_type") in {s["key"] for s in fw.raw["solution_types"]} else None
        uc = create_use_case(
            db, actor, title=form.get(f"title_{i}") or c["title"], role=c["role"], need=c["need"], outcome=c["outcome"],
            gap_statement=c["gap_statement"], domain=domain, solution_type=sol, intake_round_id=round_id,
            workshop_answers=c.get("answers") or {},
        )
        record(db, uc, actor, "ai", "Drafted from workshop notes and accepted by facilitator", evidence=c.get("evidence", []))
        created.append(uc.ref)
    db.commit()
    return redirect(f"/rounds/{round_id}", msg=f"Added {len(created)} use case(s): {', '.join(created)}" if created else "Nothing selected")
