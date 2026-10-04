"""Unity Catalog adapter (Databricks).

Searches table names, comments and column names through
system.information_schema via a SQL warehouse, with named parameters.
Metadata only: no table data is read.

Auth uses Databricks SDK unified auth (DATABRICKS_HOST + DATABRICKS_TOKEN, OAuth
M2M, or the app's own service principal when running as a Databricks App).
The principal needs USE CATALOG / USE SCHEMA / BROWSE on catalogues in scope
and CAN USE on the warehouse.

Status: written against the documented SDK and information_schema; not yet
exercised against a live workspace. Test in a sandbox workspace first.
"""
from __future__ import annotations

from collections import defaultdict

from .base import CatalogAdapter, CatalogError, TableInfo, clean_terms, infer_layer


class UnityCatalogAdapter(CatalogAdapter):
    name = "unity_catalog"
    dialect = "Databricks SQL"

    def __init__(self, warehouse_id: str, catalogs: str = ""):
        if not warehouse_id:
            raise CatalogError("UC_WAREHOUSE_ID is required for the unity_catalog adapter")
        try:
            from databricks.sdk import WorkspaceClient
        except ImportError as exc:  # pragma: no cover
            raise CatalogError("pip install databricks-sdk") from exc
        self.client = WorkspaceClient()
        self.warehouse_id = warehouse_id
        self.catalogs = [c.strip() for c in catalogs.split(",") if c.strip()]

    def describe(self) -> str:
        scope = ", ".join(self.catalogs) or "all visible catalogues"
        return f"Unity Catalog via warehouse {self.warehouse_id} ({scope})"

    # --- helpers -------------------------------------------------------------
    def _query(self, sql: str, params: dict[str, str]) -> list[dict]:
        from databricks.sdk.service.sql import StatementParameterListItem, StatementState

        resp = self.client.statement_execution.execute_statement(
            statement=sql,
            warehouse_id=self.warehouse_id,
            parameters=[StatementParameterListItem(name=k, value=v) for k, v in params.items()],
            wait_timeout="30s",
        )
        state = resp.status.state if resp.status else None
        if state != StatementState.SUCCEEDED:
            msg = resp.status.error.message if resp.status and resp.status.error else state
            raise CatalogError(f"Catalogue query failed: {msg}")
        cols = [c.name for c in resp.manifest.schema.columns]
        rows = (resp.result.data_array if resp.result else None) or []
        return [dict(zip(cols, r)) for r in rows]

    def _scope_clause(self, params: dict[str, str], alias: str) -> str:
        if not self.catalogs:
            return ""
        names = []
        for i, cat in enumerate(self.catalogs):
            params[f"c{i}"] = cat
            names.append(f":c{i}")
        return f" AND {alias}.table_catalog IN ({', '.join(names)})"

    # --- search --------------------------------------------------------------
    def search(self, terms: list[str], limit: int = 8) -> list[TableInfo]:
        terms = clean_terms(terms)
        if not terms:
            return []
        params: dict[str, str] = {}
        like_t, like_c = [], []
        for i, term in enumerate(terms):
            params[f"p{i}"] = f"%{term}%"
            like_t.append(f"lower(t.table_name) LIKE :p{i} OR lower(coalesce(t.comment, '')) LIKE :p{i}")
            like_c.append(f"lower(c.column_name) LIKE :p{i}")
        scope_t = self._scope_clause(params, "t")
        scope_c = scope_t.replace("t.table_catalog", "c.table_catalog")
        sql = f"""
WITH name_hits AS (
  SELECT t.table_catalog, t.table_schema, t.table_name, 3 AS w
  FROM system.information_schema.tables t
  WHERE t.table_schema <> 'information_schema' AND ({' OR '.join(like_t)}){scope_t}
), col_hits AS (
  SELECT c.table_catalog, c.table_schema, c.table_name, 1 AS w
  FROM system.information_schema.columns c
  WHERE c.table_schema <> 'information_schema' AND ({' OR '.join(like_c)}){scope_c}
), ranked AS (
  SELECT table_catalog, table_schema, table_name, sum(w) AS score
  FROM (SELECT * FROM name_hits UNION ALL SELECT * FROM col_hits)
  GROUP BY 1, 2, 3
)
SELECT r.table_catalog, r.table_schema, r.table_name, r.score,
       t.comment, t.table_owner, cast(t.last_altered AS string) AS last_altered
FROM ranked r
JOIN system.information_schema.tables t
  ON t.table_catalog = r.table_catalog AND t.table_schema = r.table_schema AND t.table_name = r.table_name
ORDER BY r.score DESC
LIMIT {int(limit)}"""
        rows = self._query(sql, params)
        if not rows:
            return []
        tables = {
            f"{r['table_catalog']}.{r['table_schema']}.{r['table_name']}": TableInfo(
                full_name=f"{r['table_catalog']}.{r['table_schema']}.{r['table_name']}",
                description=r.get("comment") or "",
                layer=infer_layer(r["table_catalog"], r["table_schema"]),
                owner=r.get("table_owner") or "",
                last_updated=r.get("last_altered") or "",
                matched_on=[t for t in terms if t in f"{r['table_name']} {r.get('comment') or ''}".lower()],
            )
            for r in rows
        }
        self._attach_columns_and_tags(tables)
        return list(tables.values())

    def _attach_columns_and_tags(self, tables: dict[str, TableInfo]) -> None:
        params: dict[str, str] = {}
        keys = []
        for i, name in enumerate(tables):
            params[f"n{i}"] = name
            keys.append(f":n{i}")
        in_list = ", ".join(keys)
        cols = self._query(
            f"""SELECT concat_ws('.', table_catalog, table_schema, table_name) AS fq, column_name, data_type, comment
FROM system.information_schema.columns
WHERE concat_ws('.', table_catalog, table_schema, table_name) IN ({in_list})
ORDER BY fq, ordinal_position""",
            params,
        )
        by_table: dict[str, list] = defaultdict(list)
        for c in cols:
            by_table[c["fq"]].append({"name": c["column_name"], "type": c.get("data_type") or "", "comment": c.get("comment") or ""})
        for fq, columns in by_table.items():
            tables[fq].columns = columns[:60]
        try:
            tags = self._query(
                f"""SELECT concat_ws('.', catalog_name, schema_name, table_name) AS fq, tag_name, tag_value
FROM system.information_schema.table_tags
WHERE concat_ws('.', catalog_name, schema_name, table_name) IN ({in_list})""",
                params,
            )
            for t in tags:
                tables[t["fq"]].tags[t["tag_name"]] = t.get("tag_value") or ""
        except CatalogError:
            pass  # tags are optional evidence
