from __future__ import annotations

from pathlib import Path

import yaml

from .base import CatalogAdapter, TableInfo, clean_terms, infer_layer


class DemoCatalog(CatalogAdapter):
    """Synthetic catalogue loaded from YAML, for demos and tests."""

    name = "demo"
    dialect = "Databricks SQL"

    def __init__(self, path: str):
        self.path = Path(path)
        raw = yaml.safe_load(self.path.read_text()) if self.path.exists() else {"tables": []}
        self.dialect = raw.get("dialect", self.dialect)
        self.tables = []
        for t in raw.get("tables", []):
            parts = t["full_name"].split(".")
            self.tables.append(TableInfo(
                full_name=t["full_name"],
                description=t.get("description", ""),
                layer=t.get("layer") or infer_layer(*parts[:-1]),
                owner=t.get("owner", ""),
                tags=t.get("tags", {}),
                columns=[{"name": c, "type": "", "comment": ""} if isinstance(c, str) else c for c in t.get("columns", [])],
                last_updated=t.get("last_updated", ""),
            ))

    def describe(self) -> str:
        return f"demo catalogue ({len(self.tables)} synthetic tables)"

    def search(self, terms: list[str], limit: int = 8) -> list[TableInfo]:
        terms = clean_terms(terms)
        scored = []
        for t in self.tables:
            hay_name = t.full_name.lower()
            hay_desc = t.description.lower()
            cols = " ".join(c["name"].lower() for c in t.columns)
            hits = [term for term in terms if term in hay_name or term in hay_desc or term in cols]
            if hits:
                weight = sum(3 if term in hay_name else 1 for term in hits)
                scored.append((weight, t, hits))
        scored.sort(key=lambda x: (-x[0], {"gold": 0, "silver": 1, "bronze": 2}.get(x[1].layer, 3)))
        out = []
        for _, t, hits in scored[:limit]:
            t2 = TableInfo(**{**t.to_dict(), "matched_on": hits})
            out.append(t2)
        return out
