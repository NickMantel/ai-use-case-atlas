"""Runtime settings (environment variables) and framework loading."""
from __future__ import annotations

import copy
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
FRAMEWORK_DIR = ROOT / "frameworks"


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


@dataclass(frozen=True)
class Settings:
    # Persistence. SQLite for laptops and demos; Postgres for shared deployments
    # (Cloud SQL, Azure Database for PostgreSQL, Databricks Lakebase).
    database_url: str = field(default_factory=lambda: _env("DATABASE_URL", f"sqlite:///{ROOT / 'data' / 'atlas.db'}"))
    framework: str = field(default_factory=lambda: _env("FRAMEWORK", "default"))

    # Model route: stub | anthropic | vertex | databricks | openai_compatible
    llm_provider: str = field(default_factory=lambda: _env("LLM_PROVIDER", "stub"))
    llm_model: str = field(default_factory=lambda: _env("LLM_MODEL", ""))
    llm_max_tokens: int = field(default_factory=lambda: int(_env("LLM_MAX_TOKENS", "4096")))
    llm_timeout_s: float = field(default_factory=lambda: float(_env("LLM_TIMEOUT_S", "120")))
    # openai_compatible: Databricks Model Serving, Azure OpenAI (v1 endpoint), any OpenAI-style gateway
    openai_base_url: str = field(default_factory=lambda: _env("OPENAI_BASE_URL"))
    openai_api_key: str = field(default_factory=lambda: _env("OPENAI_API_KEY"))
    # vertex: Claude on Vertex AI
    vertex_project: str = field(default_factory=lambda: _env("VERTEX_PROJECT"))
    vertex_region: str = field(default_factory=lambda: _env("VERTEX_REGION", "global"))

    # Catalogue adapter for sizing evidence: demo | unity_catalog | bigquery | none
    catalog_adapter: str = field(default_factory=lambda: _env("CATALOG_ADAPTER", "demo"))
    catalog_demo_file: str = field(default_factory=lambda: _env("CATALOG_DEMO_FILE", str(ROOT / "data" / "demo_catalog.yaml")))
    # Unity Catalog (Databricks SDK unified auth handles host/token/OAuth)
    uc_warehouse_id: str = field(default_factory=lambda: _env("UC_WAREHOUSE_ID"))
    uc_catalogs: str = field(default_factory=lambda: _env("UC_CATALOGS"))  # comma separated; empty = all visible
    # BigQuery
    bq_project: str = field(default_factory=lambda: _env("BQ_PROJECT"))
    bq_region: str = field(default_factory=lambda: _env("BQ_REGION", "australia-southeast1"))

    seed_demo_data: bool = field(default_factory=lambda: _env("SEED_DEMO_DATA", "true").lower() == "true")


@lru_cache
def get_settings() -> Settings:
    return Settings()


def _deep_merge(base: dict, overlay: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


class Framework:
    """Typed-ish accessors over the merged framework YAML."""

    def __init__(self, raw: dict[str, Any]):
        self.raw = raw

    def __getitem__(self, key: str) -> Any:
        return self.raw[key]

    # --- scoring -----------------------------------------------------------
    @property
    def levels(self) -> list[dict]:
        return self.raw["scoring"]["levels"]

    @property
    def level_points(self) -> dict[str, int]:
        return {lvl["key"]: lvl["points"] for lvl in self.levels}

    @property
    def level_labels(self) -> dict[str, str]:
        return {lvl["key"]: lvl["label"] for lvl in self.levels}

    @property
    def lenses(self) -> list[dict]:
        return self.raw["scoring"]["lenses"]

    @property
    def lens_keys(self) -> list[str]:
        return [lens["key"] for lens in self.lenses]

    # --- sizing ------------------------------------------------------------
    @property
    def sizes(self) -> list[dict]:
        return self.raw["sizing"]["sizes"]

    @property
    def size_by_key(self) -> dict[str, dict]:
        return {s["key"]: s for s in self.sizes}

    def size_for(self, scope: str | None, effort: str | None) -> str | None:
        if not scope or not effort:
            return None
        return self.raw["sizing"]["matrix"].get(scope, {}).get(effort)

    # --- workflow ----------------------------------------------------------
    @property
    def statuses(self) -> list[dict]:
        return self.raw["workflow"]["statuses"]

    @property
    def status_labels(self) -> dict[str, str]:
        return {s["key"]: s["label"] for s in self.statuses}

    def stage_for_status(self, status: str) -> dict | None:
        for stage in self.raw["workflow"]["stages"]:
            if status in stage["statuses"]:
                return stage
        return None

    # --- canvas ------------------------------------------------------------
    @property
    def canvas_sections(self) -> list[dict]:
        return self.raw["lean_canvas"]["sections"]

    @property
    def workshop_questions(self) -> list[dict]:
        out = []
        for section in self.raw["workshop"]["sections"]:
            for q in section["questions"]:
                out.append({**q, "section": section["key"], "section_title": section["title"]})
        return out


def load_framework(name: str | None = None) -> Framework:
    name = name or get_settings().framework
    base = yaml.safe_load((FRAMEWORK_DIR / "default.yaml").read_text())
    if name and name != "default":
        overlay_path = FRAMEWORK_DIR / f"{name}.yaml"
        if not overlay_path.exists():
            raise FileNotFoundError(f"Framework overlay not found: {overlay_path}")
        base = _deep_merge(base, yaml.safe_load(overlay_path.read_text()) or {})
    return Framework(base)


@lru_cache
def get_framework() -> Framework:
    return load_framework()
