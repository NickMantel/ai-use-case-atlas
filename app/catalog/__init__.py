from __future__ import annotations

from functools import lru_cache

from ..config import get_settings
from .base import CatalogAdapter, CatalogError, NullCatalog, TableInfo


def build_catalog(name: str | None = None) -> CatalogAdapter:
    s = get_settings()
    name = (name or s.catalog_adapter).lower()
    if name in ("", "none"):
        return NullCatalog()
    if name == "demo":
        from .demo import DemoCatalog

        return DemoCatalog(s.catalog_demo_file)
    if name == "unity_catalog":
        from .unity_catalog import UnityCatalogAdapter

        return UnityCatalogAdapter(s.uc_warehouse_id, s.uc_catalogs)
    if name == "bigquery":
        from .bigquery import BigQueryAdapter

        return BigQueryAdapter(s.bq_project, s.bq_region)
    raise CatalogError(f"Unknown CATALOG_ADAPTER '{name}'")


@lru_cache
def get_catalog() -> CatalogAdapter:
    return build_catalog()


__all__ = ["CatalogAdapter", "CatalogError", "TableInfo", "build_catalog", "get_catalog"]
