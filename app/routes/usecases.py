from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..catalog import get_catalog
from ..config import get_framework
from ..db import get_db
from ..models import IntakeRound, UseCase
from ..providers import get_provider
from ..services import ai, exports
from ..services import usecases as svc
from ..services.ranking import explain, flags_for, priority_score, rank
from ..web import current_user, redirect, render

router = APIRouter(prefix="/usecases")
TABS = ("overview", "qualify", "size", "score", "canvas", "accelerators", "history")


def _get(db: Session, ref: str) -> UseCase:
    uc = db.scalar(select(UseCase).where(UseCase.ref == ref))
    if not uc:
        raise HTTPException(404, f"{ref} not found")
    return uc


def _answers_from_form(form) -> dict[str, str]:
    fw = get_framework()
    return {q["key"]: (form.get(f"answer_{q['key']}") or "").strip() for q in fw.workshop_questions if f"answer_{q['key']}" in form}


# --- capture -------------------------------------------------------------------
@router.get("/new")
def new_form(request: Request, round_id: int | None = None, db: Session = Depends(get_db)):
    rounds = list(db.scalars(select(IntakeRound).order_by(IntakeRound.created_at.desc())))
    return render(request, "usecase_new.html", rounds=rounds, round_id=round_id)


@router.post("/new")
async def create(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    actor, _ = current_user(request)
    fields = {k: (form.get(k) or "").strip() or None for k in svc.EDITABLE_FIELDS if k in form}
    if fields.get("intake_round_id"):
        fields["intake_round_id"] = int(fields["intake_round_id"])
    uc = svc.create_use_case(db, actor, workshop_answers=_answers_from_form(form), **fields)
    db.commit()
    if form.get("then") == "draft":
        return redirect(f"/usecases/{uc.ref}/draft-story", msg=f"{uc.ref} captured")
    if form.get("then") == "another":
        return redirect(f"/usecases/new?round_id={uc.intake_round_id or ''}", msg=f"{uc.ref} captured. Ready for the next one.")
    return redirect(f"/usecases/{uc.ref}", msg=f"{uc.ref} captured")


# --- detail --------------------------------------------------------------------
@router.get("/{ref}")
def detail(ref: str, request: Request, tab: str = "overview", db: Session = Depends(get_db)):
    fw = get_framework()
    uc = _get(db, ref)
    tab = tab if tab in TABS else "overview"
    score = priority_score(fw, uc.scores)
    rounds = list(db.scalars(select(IntakeRound).order_by(IntakeRound.created_at.desc())))
    peers = rank(fw, [u for u in db.scalars(select(UseCase)) if u.status not in ("parked", "rejected", "merged")])
    computed_rank = next((p.computed_rank for p in peers if p.use_case.id == uc.id), None)
    return render(request, "usecase_detail.html", uc=uc, tab=tab, score=score, flags=flags_for(fw, uc.scores),
                  explanation=explain(fw, uc, score), rounds=rounds, computed_rank=computed_rank,
                  stage=fw.stage_for_status(uc.status))


@router.post("/{ref}/edit")
async def edit(ref: str, request: Request, db: Session = Depends(get_db)):
    uc = _get(db, ref)
    form = await request.form()
    actor, _ = current_user(request)
    values = {k: (form.get(k) or "").strip() for k in svc.EDITABLE_FIELDS if k in form}
    if "intake_round_id" in values:
        values["intake_round_id"] = int(values["intake_round_id"]) if values["intake_round_id"] else None
    changed = svc.update_fields(db, uc, actor, values, _answers_from_form(form))
    db.commit()
    return redirect(f"/usecases/{ref}", msg="Saved" if changed else "No changes")


@router.post("/{ref}/status")
def change_status(ref: str, request: Request, status: str = Form(...), comment: str = Form(""), db: Session = Depends(get_db)):
    uc = _get(db, ref)
    actor, _ = current_user(request)
    try:
        svc.set_status(db, get_framework(), uc, actor, status, comment.strip())
    except ValueError as exc:
        return redirect(f"/usecases/{ref}", err=str(exc))
    db.commit()
    return redirect(f"/usecases/{ref}", msg="Status updated")


# --- story drafting (HTMX partial) ---------------------------------------------
@router.post("/{ref}/ai/story", response_class=HTMLResponse)
def ai_story(ref: str, request: Request, db: Session = Depends(get_db)):
    uc = _get(db, ref)
    try:
        draft = ai.draft_story(get_provider(), get_framework(), uc)
    except ai.AIUnavailable as exc:
        return render(request, "partials/ai_error.html", error=str(exc))
    return render(request, "partials/story_suggestion.html", uc=uc, draft=draft)


@router.get("/{ref}/draft-story")
def draft_story_page(ref: str, request: Request, db: Session = Depends(get_db)):
    uc = _get(db, ref)
    try:
        draft = ai.draft_story(get_provider(), get_framework(), uc)
    except ai.AIUnavailable as exc:
        return redirect(f"/usecases/{ref}", err=f"AI drafting failed: {exc}")
    return render(request, "usecase_story_review.html", uc=uc, draft=draft)


@router.post("/{ref}/story/apply")
def apply_story(ref: str, request: Request, title: str = Form(""), role: str = Form(""), need: str = Form(""),
                outcome: str = Form(""), gap_statement: str = Form(""), solution_type: str = Form(""), db: Session = Depends(get_db)):
    uc = _get(db, ref)
    actor, _ = current_user(request)
    values = {"title": title, "role": role, "need": need, "outcome": outcome, "gap_statement": gap_statement}
    if solution_type:
        values["solution_type"] = solution_type
    svc.update_fields(db, uc, actor, {k: v.strip() for k, v in values.items() if v.strip()})
    svc.record(db, uc, actor, "ai", "Accepted AI-drafted story and gap statement")
    if uc.status == "captured":
        svc.set_status(db, get_framework(), uc, actor, "in_review")
    db.commit()
    return redirect(f"/usecases/{ref}", msg="Story updated")


# --- qualification -------------------------------------------------------------
@router.post("/{ref}/qualify")
async def qualify(ref: str, request: Request, db: Session = Depends(get_db)):
    fw = get_framework()
    uc = _get(db, ref)
    form = await request.form()
    actor, _ = current_user(request)
    checks = {c["key"]: form.get(f"check_{c['key']}") == "on" for c in fw.raw["qualification"]["checks"]}
    outcome = form.get("outcome", "qualified")
    note = (form.get("note") or "").strip()
    if outcome != "qualified" and not note:
        return redirect(f"/usecases/{ref}?tab=qualify", err="Add a note explaining the decision, so the stakeholder knows what is needed.")
    if outcome == "qualified" and not all(checks.values()) and not note:
        return redirect(f"/usecases/{ref}?tab=qualify", err="Not every check is met. Add a note explaining why it is qualified anyway.")
    svc.qualify(db, fw, uc, actor, checks, outcome, note, (form.get("merged_into") or "").strip().upper() or None)
    db.commit()
    nxt = "size" if outcome == "qualified" else "qualify"
    return redirect(f"/usecases/{ref}?tab={nxt}", msg=f"Qualification recorded: {outcome}")


# --- sizing --------------------------------------------------------------------
@router.post("/{ref}/ai/size")
def ai_size(ref: str, request: Request, db: Session = Depends(get_db)):
    uc = _get(db, ref)
    actor, _ = current_user(request)
    try:
        suggestion, evidence = ai.suggest_sizing(get_provider(), get_catalog(), get_framework(), uc)
    except ai.AIUnavailable as exc:
        return redirect(f"/usecases/{ref}?tab=size", err=f"AI sizing failed: {exc}")
    uc.sizing_suggestion, uc.catalog_evidence = suggestion, evidence
    svc.record(db, uc, actor, "ai", f"Sizing suggested: {suggestion.get('suggested_size')} (effort from {suggestion['effort_basis']})")
    db.commit()
    msg = "Sizing suggestion ready"
    if evidence.get("error"):
        msg += f" (catalogue unavailable: {evidence['error'][:120]})"
    return redirect(f"/usecases/{ref}?tab=size", msg=msg)


@router.post("/{ref}/size")
def save_size(ref: str, request: Request, cell: str = Form(""), scope_level: str = Form(""), effort_level: str = Form(""),
              rationale: str = Form(""), source: str = Form("human"), db: Session = Depends(get_db)):
    uc = _get(db, ref)
    if cell and "|" in cell:
        scope_level, effort_level = cell.split("|", 1)
    actor, _ = current_user(request)
    try:
        svc.apply_sizing(db, get_framework(), uc, actor, scope_level, effort_level, rationale.strip(), source)
    except ValueError as exc:
        return redirect(f"/usecases/{ref}?tab=size", err=str(exc))
    db.commit()
    return redirect(f"/usecases/{ref}?tab=score", msg=f"Sized {uc.size}")


# --- scoring -------------------------------------------------------------------
@router.post("/{ref}/ai/score")
def ai_score(ref: str, request: Request, db: Session = Depends(get_db)):
    uc = _get(db, ref)
    actor, _ = current_user(request)
    try:
        uc.score_suggestion = ai.suggest_scores(get_provider(), get_framework(), uc)
    except ai.AIUnavailable as exc:
        return redirect(f"/usecases/{ref}?tab=score", err=f"AI scoring failed: {exc}")
    lv = uc.score_suggestion["lenses"]
    svc.record(db, uc, actor, "ai", "DFV suggested: " + ", ".join(f"{k[0].upper()}={v['level']}" for k, v in lv.items()))
    db.commit()
    return redirect(f"/usecases/{ref}?tab=score", msg="Scoring suggestion ready. Review before saving.")


@router.post("/{ref}/score")
async def save_score(ref: str, request: Request, db: Session = Depends(get_db)):
    fw = get_framework()
    uc = _get(db, ref)
    form = await request.form()
    actor, _ = current_user(request)
    scores = {k: form.get(f"level_{k}") for k in fw.lens_keys if form.get(f"level_{k}")}
    notes = {k: (form.get(f"note_{k}") or "").strip() for k in fw.lens_keys}
    if len(scores) != len(fw.lens_keys):
        return redirect(f"/usecases/{ref}?tab=score", err="Rate every lens before saving")
    svc.apply_scores(db, fw, uc, actor, scores, notes, form.get("source", "human"))
    db.commit()
    return redirect(f"/usecases/{ref}?tab=score", msg=f"Scores saved. Priority score {uc.priority_score:g}/100")


@router.post("/{ref}/rank")
def set_rank(ref: str, request: Request, agreed_rank: str = Form(""), db: Session = Depends(get_db)):
    uc = _get(db, ref)
    actor, _ = current_user(request)
    value = int(agreed_rank) if agreed_rank.strip().isdigit() else None
    svc.set_agreed_rank(db, uc, actor, value)
    if value and uc.status == "scored":
        svc.set_status(db, get_framework(), uc, actor, "prioritised", "Rank agreed at portfolio review")
    db.commit()
    return redirect(request.headers.get("referer") or f"/usecases/{ref}?tab=score", msg="Agreed rank updated")


# --- lean canvas ---------------------------------------------------------------
@router.post("/{ref}/ai/canvas")
def ai_canvas(ref: str, request: Request, db: Session = Depends(get_db)):
    uc = _get(db, ref)
    actor, _ = current_user(request)
    try:
        canvas = ai.draft_canvas(get_provider(), get_framework(), uc)
    except ai.AIUnavailable as exc:
        return redirect(f"/usecases/{ref}?tab=canvas", err=f"Canvas generation failed: {exc}")
    svc.save_canvas(db, uc, actor, canvas, generated=True)
    db.commit()
    return redirect(f"/usecases/{ref}?tab=canvas", msg="Lean Canvas drafted. Edit anything that is wrong, then save.")


@router.post("/{ref}/canvas")
async def save_canvas(ref: str, request: Request, db: Session = Depends(get_db)):
    fw = get_framework()
    uc = _get(db, ref)
    form = await request.form()
    actor, _ = current_user(request)
    canvas = {s["key"]: (form.get(f"canvas_{s['key']}") or "").strip() for s in fw.canvas_sections}
    svc.save_canvas(db, uc, actor, canvas)
    db.commit()
    return redirect(f"/usecases/{ref}?tab=canvas", msg="Canvas saved")


@router.get("/{ref}/canvas.pptx")
def canvas_pptx(ref: str, db: Session = Depends(get_db)):
    uc = _get(db, ref)
    data = exports.lean_canvas_pptx(get_framework(), [uc])
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                    headers={"Content-Disposition": f'attachment; filename="{uc.ref}-lean-canvas.pptx"'})


@router.get("/{ref}/canvas/print")
def canvas_print(ref: str, request: Request, db: Session = Depends(get_db)):
    return render(request, "canvas_print.html", uc=_get(db, ref))


# --- accelerators --------------------------------------------------------------
@router.post("/{ref}/ai/sql")
def ai_sql(ref: str, request: Request, db: Session = Depends(get_db)):
    uc = _get(db, ref)
    actor, _ = current_user(request)
    try:
        result = ai.draft_sql(get_provider(), get_catalog(), get_framework(), uc)
    except ai.AIUnavailable as exc:
        return redirect(f"/usecases/{ref}?tab=accelerators", err=f"SQL generation failed: {exc}")
    notes = "\n".join(f"--   {a}" for a in result["assumptions"])
    uc.starter_sql = f"-- {result['explanation']}\n" + (f"-- Assumptions:\n{notes}\n" if notes else "") + result["sql"]
    svc.record(db, uc, actor, "ai", "Starter SQL generated (not executed)")
    db.commit()
    return redirect(f"/usecases/{ref}?tab=accelerators", msg="Starter SQL drafted. It has not been run.")


@router.post("/{ref}/ai/mockup")
def ai_mockup(ref: str, request: Request, db: Session = Depends(get_db)):
    uc = _get(db, ref)
    actor, _ = current_user(request)
    try:
        result = ai.draft_mockup(get_provider(), get_framework(), uc)
    except ai.AIUnavailable as exc:
        return redirect(f"/usecases/{ref}?tab=accelerators", err=f"Mock-up generation failed: {exc}")
    uc.mockup_html = result["html"]
    svc.record(db, uc, actor, "ai", "UI mock-up generated")
    db.commit()
    return redirect(f"/usecases/{ref}?tab=accelerators", msg="Mock-up drafted")


@router.get("/{ref}/mockup")
def mockup(ref: str, db: Session = Depends(get_db)):
    uc = _get(db, ref)
    # Model-generated HTML: serve in a locked-down sandbox (no scripts, no network).
    csp = "sandbox; default-src 'none'; style-src 'unsafe-inline'; img-src data:; font-src data:"
    return HTMLResponse(uc.mockup_html or "<p>No mock-up yet.</p>", headers={"Content-Security-Policy": csp, "X-Content-Type-Options": "nosniff"})
