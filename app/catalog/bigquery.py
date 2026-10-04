"""BigQuery adapter (GCP).

Searches table names, descriptions and column names across a project's
region-level INFORMATION_SCHEMA with query parameters. Metadata only.

Auth uses Application Default Credentials (Cloud Run service account, or
`gcloud auth application-default login` locally). The principal needs
bigquery.tables.list / metadata viewer on datasets in scope and
bigquery.jobs.create on the project.

Status: written against documented INFORMATION_SCHEMA views; not yet
exercised against a live project. Test in a sandbox project first.
"""
from __future__ import annotations

import json
from collections import defaultdict

from .base import CatalogAdapter, CatalogError, TableInfo, clean_terms, infer_layer


class BigQueryAdapter(CatalogAdapter):
    name = "bigquery"
    dialect = "BigQuery Standard SQL"

    def __init__(self, project: str, region: str):
        if not project:
            raise CatalogError("BQ_PROJECT is required for the bigquery adapter")
        try:
            from google.cloud import bigquery
        except ImportError as exc:  # pragma: no cover
            raise CatalogError("pip install google-cloud-bigquery") from exc
        self.bq = bigquery
        self.client = bigquery.Client(project=project)
        self.project = project
        self.region = region

    def describe(self) -> str:
        return f"BigQuery {self.project} ({self.region})"

    def _schema(self, view: str) -> str:
        return f"`{self.project}`.`region-{self.region}`.INFORMATION_SCHEMA.{view}"

    def _query(self, sql: str, params: list) -> list[dict]:
        try:
            job = self.client.query(sql, job_config=self.bq.QueryJobConfig(query_parameters=params))
            return [dict(r) for r in job.result(timeout=30)]
        except Exception as exc:  # google.api_core exceptions vary by version
            raise CatalogError(f"Catalogue query failed: {exc}") from exc

    def search(self, terms: list[str], limit: int = 8) -> list[TableInfo]:
        terms = clean_terms(terms)
        if not terms:
            return []
        P = self.bq.ScalarQueryParameter
        params = [P(f"p{i}", "STRING", f"%{t}%") for i, t in enumerate(terms)]
        like_t = " OR ".join(f"LOWER(t.table_name) LIKE @p{i} OR LOWER(IFNULL(o.option_value, '')) LIKE @p{i}" for i in range(len(terms)))
        like_c = " OR ".join(f"LOWER(c.column_name) LIKE @p{i}" for i in range(len(terms)))
        sql = f"""
WITH descr AS (
  SELECT table_catalog, table_schema, table_name, option_value
  FROM {self._schema('TABLE_OPTIONS')} WHERE option_name = 'description'
), name_hits AS (
  SELECT t.table_catalog, t.table_schema, t.table_name, 3 AS w
  FROM {self._schema('TABLES')} t
  LEFT JOIN descr o USING (table_catalog, table_schema, table_name)
  WHERE {like_t}
), col_hits AS (
  SELECT DISTINCT c.table_catalog, c.table_schema, c.table_name, 1 AS w
  FROM {self._schema('COLUMNS')} c
  WHERE {like_c}
), ranked AS (
  SELECT table_catalog, table_schema, table_name, SUM(w) AS score
  FROM (SELECT * FROM name_hits UNION ALL SELECT * FROM col_hits)
  GROUP BY 1, 2, 3
)
SELECT r.*, d.option_value AS description
FROM ranked r LEFT JOIN descr d USING (table_catalog, table_schema, table_name)
ORDER BY score DESC
LIMIT {int(limit)}"""
        rows = self._query(sql, params)
        if not rows:
            return []
        tables: dict[str, TableInfo] = {}
        for r in rows:
            fq = f"{r['table_catalog']}.{r['table_schema']}.{r['table_name']}"
            desc = (r.get("description") or "").strip('"')
            tables[fq] = TableInfo(
                full_name=fq,
                description=desc,
                layer=infer_layer(r["table_schema"]),
                matched_on=[t for t in terms if t in f"{r['table_name']} {desc}".lower()],
            )
        self._attach_columns_and_labels(tables)
        return list(tables.values())

    def _attach_columns_and_labels(self, tables: dict[str, TableInfo]) -> None:
        names = list(tables)
        param = self.bq.ArrayQueryParameter("names", "STRING", names)
        cols = self._query(
            f"""SELECT CONCAT(table_catalog, '.', table_schema, '.', table_name) AS fq, field_path AS column_name, data_type, description
FROM {self._schema('COLUMN_FIELD_PATHS')}
WHERE CONCAT(table_catalog, '.', table_schema, '.', table_name) IN UNNEST(@names)""",
            [param],
        )
        by_table: dict[str, list] = defaultdict(list)
        for c in cols:
            by_table[c["fq"]].append({"name": c["column_name"], "type": c.get("data_type") or "", "comment": c.get("description") or ""})
        for fq, columns in by_table.items():
            tables[fq].columns = columns[:60]
        labels = self._query(
            f"""SELECT CONCAT(table_catalog, '.', table_schema, '.', table_name) AS fq, option_value
FROM {self._schema('TABLE_OPTIONS')}
WHERE option_name = 'labels' AND CONCAT(table_catalog, '.', table_schema, '.', table_name) IN UNNEST(@names)""",
            [param],
        )
        for row in labels:
            # option_value looks like: [STRUCT("domain", "student"), STRUCT("review_status", "reviewed")]
            raw = row.get("option_value") or ""
            try:
                pairs = json.loads(raw.replace("STRUCT(", "[").replace(")", "]"))
                tables[row["fq"]].tags.update({k: v for k, v in pairs})
            except (ValueError, TypeError):
                continue
