from datetime import datetime, timezone

import pytest

from app.config import load_framework
from app.models import UseCase
from app.services.catalog_evidence import classify, effort_from_coverage
from app.services.ranking import flags_for, priority_score, rank


def _uc(ref, scores, size=None, agreed=None, minute=0):
    uc = UseCase(ref=ref, title=ref, scores=scores, size=size, agreed_rank=agreed)
    uc.created_at = datetime(2026, 10, 1, 9, minute, tzinfo=timezone.utc)
    return uc


def test_worked_example_order(fw):
    """The illustrative worked example must rank 1, 2, 3."""
    items = rank(fw, [
        _uc("budget", {"desirability": "M", "feasibility": "L", "viability": "M"}, minute=0),
        _uc("atrisk", {"desirability": "H", "feasibility": "M", "viability": "H"}, minute=1),
        _uc("teaching", {"desirability": "H", "feasibility": "H", "viability": "H"}, minute=2),
    ])
    assert [i.use_case.ref for i in items] == ["teaching", "atrisk", "budget"]
    assert [i.computed_rank for i in items] == [1, 2, 3]


def test_score_scale(fw):
    assert priority_score(fw, {"desirability": "H", "feasibility": "H", "viability": "H"}) == 100.0
    assert priority_score(fw, {"desirability": "L", "feasibility": "L", "viability": "L"}) == pytest.approx(33.3, abs=0.1)
    assert priority_score(fw, {"desirability": "H"}) is None


def test_ties_break_on_size_then_agreed_rank_wins(fw):
    hhm = {"desirability": "H", "feasibility": "H", "viability": "M"}
    big, small = _uc("big", hhm, "L"), _uc("small", hhm, "S")
    assert [i.use_case.ref for i in rank(fw, [big, small])] == ["small", "big"]
    big.agreed_rank = 1
    assert [i.use_case.ref for i in rank(fw, [big, small])] == ["big", "small"]


def test_unscored_sort_last(fw):
    items = rank(fw, [_uc("none", {}), _uc("scored", {"desirability": "M", "feasibility": "M", "viability": "M"})])
    assert items[0].use_case.ref == "scored" and items[1].computed_rank is None


def test_flags(fw):
    assert flags_for(fw, {"desirability": "H", "feasibility": "L", "viability": "M"}) == ["Data foundations needed first"]


@pytest.mark.parametrize("scope,effort,size", [("L", "L", "XS"), ("L", "M", "S"), ("M", "M", "M"), ("H", "M", "L"), ("H", "H", "XL"), ("H", "L", "M")])
def test_sizing_matrix_matches_template(fw, scope, effort, size):
    assert fw.size_for(scope, effort) == size


def test_coverage_rules():
    gold = {"layer": "gold", "tags": {"review_status": "reviewed"}}
    gold_pending = {"layer": "gold", "tags": {"review_status": "pending"}}
    silver = {"layer": "silver", "tags": {}}
    assert classify([gold]) == "reuse"
    assert classify([gold_pending, silver]) == "develop"
    assert classify([]) == "build"
    assert effort_from_coverage(["reuse", "reuse"]) == "L"
    assert effort_from_coverage(["reuse", "develop"]) == "M"
    assert effort_from_coverage(["reuse", "build"]) == "H"


def test_client_overlays_load():
    deakin = load_framework("deakin")
    assert deakin.raw["brand"]["client_name"] == "Deakin University"
    assert "EDP team" in deakin.raw["workflow"]["stages"][3]["owner"]
    assert deakin.size_for("M", "L") == "S"  # inherited from default
    assert load_framework("auspost").raw["brand"]["client_name"] == "Australia Post"
