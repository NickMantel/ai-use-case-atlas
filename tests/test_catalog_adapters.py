"""Catalogue adapters checked against fake SDK clients: queries must be
parameterised (search terms never appear in SQL text) and results parsed."""
from types import SimpleNamespace

import pytest

from app.catalog.base import infer_layer
from app.catalog.demo import DemoCatalog
from app.config import ROOT


def test_infer_layer():
    assert infer_layer("edp", "gold_student") == "gold"
    assert infer_layer("prod", "gldsrv-finance") == "gold" and infer_layer("prod", "gld_finance") == "gold"
    assert infer_layer("edp", "slv_finance") == "silver"
    assert infer_layer("raw_sis") == "bronze"


def test_demo_search_prefers_name_hits_and_gold():
    cat = DemoCatalog(str(ROOT / "data" / "demo_catalog.yaml"))
    hits = cat.search(["enrol", "unit"])
    assert hits[0].full_name == "edp.gold_student.fact_unit_enrolment"
    assert cat.search(["zzz-not-there"]) == []


def test_unity_catalog_parameterised():
    pytest.importorskip("databricks.sdk")
    from databricks.sdk.service.sql import StatementState

    from app.catalog.unity_catalog import UnityCatalogAdapter

    calls = []

    def execute_statement(statement, warehouse_id, parameters, wait_timeout):
        calls.append((statement, {p.name: p.value for p in parameters}))
        if "ranked AS" in statement:
            cols, rows = ["table_catalog", "table_schema", "table_name", "score", "comment", "table_owner", "last_altered"], [
                ["edp", "gold_student", "fact_unit_enrolment", "4", "Enrolments", "owners", "2026-09-30"]]
        elif "information_schema.columns" in statement:
            cols, rows = ["fq", "column_name", "data_type", "comment"], [["edp.gold_student.fact_unit_enrolment", "census_date", "DATE", ""]]
        else:
            cols, rows = ["fq", "tag_name", "tag_value"], [["edp.gold_student.fact_unit_enrolment", "review_status", "reviewed"]]
        return SimpleNamespace(
            status=SimpleNamespace(state=StatementState.SUCCEEDED, error=None),
            manifest=SimpleNamespace(schema=SimpleNamespace(columns=[SimpleNamespace(name=c) for c in cols])),
            result=SimpleNamespace(data_array=rows),
        )

    adapter = UnityCatalogAdapter.__new__(UnityCatalogAdapter)
    adapter.client = SimpleNamespace(statement_execution=SimpleNamespace(execute_statement=execute_statement))
    adapter.warehouse_id, adapter.catalogs = "wh1", ["edp"]
    out = adapter.search(["enrol'; DROP TABLE x;--", "unit"])
    assert out[0].layer == "gold" and out[0].tags["review_status"] == "reviewed" and out[0].columns[0]["name"] == "census_date"
    for sql, params in calls:
        assert "DROP" not in sql and "enrol" not in sql
    assert calls[0][1]["c0"] == "edp" and calls[0][1]["p0"] == "%enrol drop table x%"


def test_bigquery_parameterised():
    pytest.importorskip("google.cloud.bigquery")
    from google.cloud import bigquery

    from app.catalog.bigquery import BigQueryAdapter

    seen = []

    def query(sql, job_config):
        seen.append((sql, job_config.query_parameters))
        if "ranked AS" in sql:
            rows = [{"table_catalog": "ap-data", "table_schema": "gold_parcels", "table_name": "parcel_events", "score": 3, "description": '"Scan events"'}]
        elif "COLUMN_FIELD_PATHS" in sql:
            rows = [{"fq": "ap-data.gold_parcels.parcel_events", "column_name": "scan_ts", "data_type": "TIMESTAMP", "description": None}]
        else:
            rows = [{"fq": "ap-data.gold_parcels.parcel_events", "option_value": '[STRUCT("review_status", "reviewed")]'}]
        return SimpleNamespace(result=lambda timeout: rows)

    adapter = BigQueryAdapter.__new__(BigQueryAdapter)
    adapter.bq, adapter.client, adapter.project, adapter.region = bigquery, SimpleNamespace(query=query), "ap-data", "australia-southeast1"
    out = adapter.search(["parcel", "scan"])
    assert out[0].full_name == "ap-data.gold_parcels.parcel_events" and out[0].layer == "gold"
    assert out[0].description == "Scan events" and out[0].tags == {"review_status": "reviewed"}
    assert all("parcel" not in sql.split("WHERE", 1)[-1] for sql, _ in seen[:1])
    assert "`region-australia-southeast1`" in seen[0][0]
