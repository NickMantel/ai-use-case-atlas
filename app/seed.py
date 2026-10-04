"""Illustrative demo data (from the worked example). Loaded once into an empty
database when SEED_DEMO_DATA=true. Clearly labelled; safe to delete."""
from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import Framework
from .models import IntakeRound, UseCase
from .services.ranking import priority_score
from .services.usecases import create_use_case, record

ACTOR = "demo seed"


def seed_if_empty(db: Session, fw: Framework) -> bool:
    if db.scalar(select(func.count(UseCase.id))):
        return False
    rnd = IntakeRound(
        name="Illustrative workshop: teaching, students and finance",
        held_on=date(2026, 10, 1),
        domain=None,
        facilitator="Data platform team",
        attendees="Faculty workload planner, Student success lead, Finance business partner",
        notes="Illustrative data based on the worked example. Delete once real intake starts.",
    )
    db.add(rnd)
    db.flush()

    items = [
        dict(
            title="Teaching demand forecast", domain=fw.raw["domains"][0], solution_type="analytics",
            role="faculty workload planner", need="an early view of unit enrolment trends",
            outcome="I can adjust tutor allocations before term starts",
            gap_statement="Today tutor allocations are set from last year's numbers and corrected after census, causing late hires and overloaded tutors. Ideally planners see projected enrolments per unit six weeks before term.",
            use_case_lead="Faculty operations manager", sponsor="Associate Dean, Teaching",
            workshop_answers={
                "time_lost": "Rebuilding the allocation spreadsheet every trimester from three exports.",
                "low_confidence_decision": "How many tutors to book per unit before census.",
                "untrusted_numbers": "Enrolment counts differ between the student system report and faculty spreadsheets.",
                "stop_doing": "Manual reconciliations and last-minute casual hires.",
                "better_decision": "Workload planners, about four weeks earlier.",
                "six_months": "Projected enrolments per unit visible before allocations are locked.",
            },
            status="prioritised", scope_level="M", effort_level="L", scores={"desirability": "H", "feasibility": "H", "viability": "H"},
            canvas={
                "business_problem": "- Tutor allocations are set from prior-year numbers and corrected after census\n- Late casual hires and uneven tutor load",
                "solution_description": "- Unit-level enrolment projection refreshed weekly in the lakehouse\n- Planner dashboard with projected vs allocated capacity",
                "systems_data_tech": "- Student system enrolments (gold)\n- Timetable extract\n- Lakehouse + BI tool",
                "capability_requirements": "- Data engineering\n- Time series forecasting\n- Dashboard design",
                "business_users": "- Faculty workload planners\n- Heads of school\n- Timetabling",
                "estimated_benefits": "- Allocations locked four weeks earlier\n- Fewer last-minute casual hires",
                "data_foundations": "- Conformed unit offering dimension\n- Reusable enrolment trend metric",
                "required_data": "- edp.gold_student.fact_unit_enrolment\n- edp.gold_student.dim_unit_offering\n- edp.bronze_timetable.class_sessions",
                "assumptions_risks": "- Historical enrolment patterns are predictive\n- TBC: timetable data refresh cadence",
                "estimated_resources": "- Data engineer, analyst\n- SME: faculty operations manager",
            },
        ),
        dict(
            title="At-risk student alerts", domain=fw.raw["domains"][0], solution_type="analytics",
            role="student success adviser", need="a weekly list of students showing early disengagement",
            outcome="I can reach out before the first assessment deadline",
            gap_statement="Advisers learn a student is struggling after a failed assessment. Ideally they act on engagement signals in weeks 2-4.",
            use_case_lead="Student success lead", sponsor="Director, Student Experience",
            workshop_answers={"time_lost": "Chasing LMS reports from unit chairs.", "six_months": "Advisers contact flagged students within a week."},
            status="prioritised", scope_level="M", effort_level="M", scores={"desirability": "H", "feasibility": "M", "viability": "H"},
        ),
        dict(
            title="Budget variance commentary (GenAI)", domain=fw.raw["domains"][1], solution_type="genai",
            role="finance business partner", need="a first draft of monthly variance commentary per cost centre",
            outcome="I spend month-end on conversations with budget holders rather than writing",
            gap_statement="Commentary is written by hand from GL extracts each month. Ideally a reviewed draft is ready on day 3.",
            use_case_lead="Finance business partner", sponsor="Chief Financial Officer",
            workshop_answers={"time_lost": "Two days a month writing commentary.", "untrusted_numbers": "Forecast versions differ across cost centre packs."},
            status="scored", scope_level="H", effort_level="M", scores={"desirability": "M", "feasibility": "L", "viability": "M"},
        ),
        dict(
            title="Admissions offer conversion view", domain=fw.raw["domains"][0], solution_type="bi",
            role="admissions manager", need="daily visibility of offer acceptance by program", outcome="TBC",
            gap_statement=None, use_case_lead=None, sponsor=None,
            workshop_answers={"low_confidence_decision": "Whether to release extra offers in the second round."},
            status="captured",
        ),
    ]
    for item in items:
        status = item.pop("status")
        scope, effort, scores = item.pop("scope_level", None), item.pop("effort_level", None), item.pop("scores", None)
        canvas = item.pop("canvas", None)
        uc = create_use_case(db, ACTOR, intake_round_id=rnd.id, **item)
        uc.status = status
        if scope and effort:
            uc.scope_level, uc.effort_level, uc.size = scope, effort, fw.size_for(scope, effort)
            uc.sizing_rationale = "Illustrative sizing from the worked example."
        if scores:
            uc.scores = scores
            uc.priority_score = priority_score(fw, scores)
        if canvas:
            uc.canvas = canvas
        if status != "captured":
            uc.qualification_outcome = "qualified"
            uc.qualification_checks = {c["key"]: True for c in fw.raw["qualification"]["checks"]}
        record(db, uc, ACTOR, "edited", "Loaded illustrative demo data")
    db.commit()
    return True
