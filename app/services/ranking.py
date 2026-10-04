"""Deterministic, explainable DFV ranking.

The model proposes lens ratings; this module turns agreed ratings into a
priority order with a plain-English explanation. No hidden weights: the
weights live in the framework YAML and are shown on the Framework page.

Order of precedence:
  1. Agreed rank set at a portfolio review (human decision) wins.
  2. Weighted DFV points, highest first.
  3. Smaller t-shirt size first (quicker value).
  4. Higher desirability first.
  5. Older first (first in, first considered).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..config import Framework
from ..models import UseCase

RANKABLE_STATUSES = {"scored", "prioritised", "approved"}


@dataclass
class RankedItem:
    use_case: UseCase
    score: float | None
    computed_rank: int | None = None
    flags: list[str] = field(default_factory=list)
    explanation: str = ""


def priority_score(fw: Framework, scores: dict[str, str] | None) -> float | None:
    """Weighted points normalised to 0-100. None until every lens is rated."""
    if not scores:
        return None
    points = fw.level_points
    max_pts = max(points.values())
    total = weight_sum = 0.0
    for lens in fw.lenses:
        level = scores.get(lens["key"])
        if level not in points:
            return None
        w = float(lens.get("weight", 1.0))
        total += points[level] * w
        weight_sum += max_pts * w
    return round(100.0 * total / weight_sum, 1) if weight_sum else None


def flags_for(fw: Framework, scores: dict[str, str] | None) -> list[str]:
    flag_text = fw.raw["scoring"].get("flags", {})
    low_key = min(fw.level_points, key=fw.level_points.get)
    return [flag_text[k] for k in fw.lens_keys if scores and scores.get(k) == low_key and k in flag_text]


def explain(fw: Framework, uc: UseCase, score: float | None) -> str:
    if score is None:
        return "Not yet scored on every lens."
    labels = fw.level_labels
    parts = [f"{lens['label']} {labels.get(uc.scores.get(lens['key']), '?')}" for lens in fw.lenses]
    text = f"{', '.join(parts)} gives {score:g}/100"
    if uc.size:
        size = fw.size_by_key.get(uc.size, {})
        text += f"; size {size.get('label', uc.size)} ({size.get('weeks', '')}) breaks ties"
    if uc.agreed_rank:
        text += f". Rank {uc.agreed_rank} agreed at portfolio review"
    return text + "."


def rank(fw: Framework, use_cases: list[UseCase]) -> list[RankedItem]:
    size_order = {s["key"]: s["order"] for s in fw.sizes}
    items = []
    for uc in use_cases:
        score = priority_score(fw, uc.scores)
        items.append(RankedItem(uc, score, flags=flags_for(fw, uc.scores), explanation=explain(fw, uc, score)))

    def key(item: RankedItem):
        uc = item.use_case
        return (
            uc.agreed_rank if uc.agreed_rank is not None else 10_000,
            -(item.score if item.score is not None else -1),
            size_order.get(uc.size or "", 99),
            -fw.level_points.get((uc.scores or {}).get("desirability", ""), 0),
            uc.created_at,
        )

    scored = sorted([i for i in items if i.score is not None], key=key)
    for n, item in enumerate(scored, start=1):
        item.computed_rank = n
    unscored = [i for i in items if i.score is None]
    return scored + sorted(unscored, key=lambda i: i.use_case.created_at)
