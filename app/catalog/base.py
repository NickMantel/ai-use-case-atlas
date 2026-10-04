from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from typing import Any

GOLD = re.compile(r"(^|[_\-.])(gold|gld|gldsrv|curated|mart|marts|presentation|serving|semantic)([_\-.]|$)", re.I)
SILVER = re.compile(r"(^|[_\-.])(silver|slv|conformed|clean|cleansed|integration|staging|stg)([_\-.]|$)", re.I)
BRONZE = re.compile(r"(^|[_\-.])(bronze|brz|raw|landing|ingest|source|src)([_\-.]|$)", re.I)


def infer_layer(*names: str) -> str:
    joined = ".".join(n for n in names if n)
    if GOLD.search(joined):
        return "gold"
    if SILVER.search(joined):
        return "silver"
    if BRONZE.search(joined):
        return "bronze"
    return "unknown"


@dataclass
class TableInfo:
    full_name: str
    description: str = ""
    layer: str = "unknown"
    owner: str = ""
    tags: dict[str, str] = field(default_factory=dict)
    columns: list[dict[str, str]] = field(default_factory=list)  # {name, type, comment}
    last_updated: str = ""
    matched_on: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CatalogError(RuntimeError):
    pass


class CatalogAdapter(ABC):
    """Read-only metadata search over a data catalogue. Implementations must
    use parameterised queries and must never read table contents."""

    name = "base"
    dialect = "ANSI SQL"

    @abstractmethod
    def search(self, terms: list[str], limit: int = 8) -> list[TableInfo]:
        ...

    def describe(self) -> str:
        return self.name


class NullCatalog(CatalogAdapter):
    name = "none"

    def search(self, terms: list[str], limit: int = 8) -> list[TableInfo]:
        return []

    def describe(self) -> str:
        return "no catalogue configured"


def clean_terms(terms: list[str]) -> list[str]:
    out = []
    for t in terms:
        t = re.sub(r"[^a-z0-9_ ]", "", (t or "").lower()).strip()
        if len(t) >= 3 and t not in out:
            out.append(t)
    return out[:6]
