"""Turn a list of data needs into catalogue evidence and an effort read.

Coverage per need:
  reuse    a reviewed gold-layer table matches (pipelines/models already exist)
  develop  matches exist but only in silver/bronze, or gold not yet reviewed (source is stable)
  build    nothing in the catalogue matches (build from scratch)

Effort column from coverage (deterministic, shown to the user):
  all reuse -> L; any build -> H; otherwise M.
"""
from __future__ import annotations

from typing import Any

from ..catalog import CatalogAdapter, CatalogError
from ..models import utcnow

COVERAGE_LABEL = {
    "reuse": "Reuse: already in a curated (gold) table",
    "develop": "Develop: available in raw/silver layers",
    "build": "Build: not found in the catalogue",
}


def classify(matches: list[dict[str, Any]]) -> str:
    if not matches:
        return "build"
    for m in matches:
        reviewed = (m.get("tags") or {}).get("review_status", "reviewed") != "pending"
        if m.get("layer") == "gold" and reviewed:
            return "reuse"
    return "develop"


def effort_from_coverage(coverages: list[str]) -> str | None:
    if not coverages:
        return None
    if all(c == "reuse" for c in coverages):
        return "L"
    if any(c == "build" for c in coverages):
        return "H"
    return "M"


def gather(catalog: CatalogAdapter, data_needs: list[dict[str, Any]]) -> dict[str, Any]:
    needs_out, error = [], None
    for need in data_needs:
        matches: list[dict[str, Any]] = []
        if error is None:
            try:
                matches = [t.to_dict() for t in catalog.search(need.get("search_terms") or [need.get("entity", "")], limit=5)]
            except CatalogError as exc:
                error = str(exc)
        cov = classify(matches) if error is None else "unknown"
        needs_out.append({**need, "matches": matches, "coverage": cov, "coverage_label": COVERAGE_LABEL.get(cov, "Catalogue unavailable")})
    coverages = [n["coverage"] for n in needs_out if n["coverage"] != "unknown"]
    return {
        "adapter": catalog.describe(),
        "checked_at": utcnow().isoformat(timespec="seconds"),
        "needs": needs_out,
        "effort_from_catalog": effort_from_coverage(coverages) if error is None else None,
        "error": error,
    }
