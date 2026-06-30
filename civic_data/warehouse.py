from __future__ import annotations

import csv
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any


def export_wave1_for_postgres(warehouse_root: Path, export_root: Path) -> dict[str, Any]:
    export_root.mkdir(parents=True, exist_ok=True)
    tables = {
        "ward": _export_table(
            export_root / "ward.csv",
            _read_json_list(warehouse_root / "wards.json"),
            [
                "ward_key",
                "source_id",
                "ward_number",
                "ward_name",
                "normalized_name",
                "version",
                "zone",
                "corporation",
                "assembly_constituency",
                "population",
                "evidence_json",
            ],
            _ward_row,
        ),
        "old_new_ward_mapping": _export_table(
            export_root / "old_new_ward_mapping.csv",
            _read_json_list(warehouse_root / "old_new_ward_mappings.json"),
            [
                "old_ward_number",
                "old_ward_name",
                "new_ward_number",
                "new_ward_name",
                "assembly_constituency",
                "parliamentary_constituency",
                "confidence",
                "method",
                "explanation",
                "evidence_json",
            ],
            _mapping_row,
        ),
        "issue_category": _export_table(
            export_root / "issue_category.csv",
            _read_json_list(warehouse_root / "issue_categories.json"),
            ["name", "normalized_name", "source"],
            _category_row,
        ),
        "complaint": _export_table(
            export_root / "complaint.csv",
            _read_json_list(warehouse_root / "complaints.json"),
            [
                "external_complaint_id",
                "issue_category",
                "issue_subcategory",
                "grievance_date",
                "year",
                "ward_name_raw",
                "normalized_ward_name",
                "status",
                "staff_remarks",
                "staff_name",
                "evidence_json",
            ],
            _complaint_row,
        ),
    }
    (export_root / "load_wave1.sql").write_text(_load_sql())
    manifest = {"format": "postgres_csv_wave1", "tables": tables}
    (export_root / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True))
    return manifest


def load_wave1_with_psql(database_url: str, export_root: Path) -> None:
    if not database_url:
        raise ValueError("--database-url is required")
    psql = shutil.which("psql")
    if not psql:
        raise RuntimeError("psql is not installed or not on PATH")
    sql_path = export_root / "load_wave1.sql"
    if not sql_path.exists():
        raise FileNotFoundError(f"Missing load script: {sql_path}")
    env = dict(os.environ)
    env["DATABASE_URL"] = database_url
    subprocess.run(
        [psql, database_url, "-v", "ON_ERROR_STOP=1", "-f", str(sql_path)],
        cwd=export_root,
        check=True,
        env=env,
    )


def _read_json_list(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON file: {path}") from exc
    if not isinstance(data, list):
        raise ValueError(f"{path} must contain a JSON list")
    return [item for item in data if isinstance(item, dict)]


def _export_table(
    path: Path,
    records: list[dict[str, Any]],
    fieldnames: list[str],
    transform,
) -> dict[str, int | str]:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            writer.writerow(transform(record))
    return {"path": path.name, "rows": len(records)}


def _ward_row(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "ward_key": item.get("ward_key", ""),
        "source_id": item.get("source_id", ""),
        "ward_number": item.get("ward_number", ""),
        "ward_name": item.get("ward_name", ""),
        "normalized_name": item.get("normalized_name", ""),
        "version": item.get("version", ""),
        "zone": item.get("zone", ""),
        "corporation": item.get("corporation", ""),
        "assembly_constituency": item.get("assembly_constituency", ""),
        "population": item.get("population", ""),
        "evidence_json": _json_cell(item.get("evidence", {})),
    }


def _mapping_row(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "old_ward_number": item.get("old_ward_number", ""),
        "old_ward_name": item.get("old_ward_name", ""),
        "new_ward_number": item.get("new_ward_number", ""),
        "new_ward_name": item.get("new_ward_name", ""),
        "assembly_constituency": item.get("assembly_constituency", ""),
        "parliamentary_constituency": item.get("parliamentary_constituency", ""),
        "confidence": item.get("confidence", ""),
        "method": item.get("method", ""),
        "explanation": item.get("explanation", ""),
        "evidence_json": _json_cell(item.get("evidence", {})),
    }


def _category_row(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": item.get("name", ""),
        "normalized_name": item.get("normalized_name", ""),
        "source": item.get("source", ""),
    }


def _complaint_row(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "external_complaint_id": item.get("external_complaint_id", ""),
        "issue_category": item.get("issue_category", ""),
        "issue_subcategory": item.get("issue_subcategory", ""),
        "grievance_date": item.get("grievance_date", ""),
        "year": item.get("year", ""),
        "ward_name_raw": item.get("ward_name_raw", ""),
        "normalized_ward_name": item.get("normalized_ward_name", ""),
        "status": item.get("status", ""),
        "staff_remarks": item.get("staff_remarks", ""),
        "staff_name": item.get("staff_name", ""),
        "evidence_json": _json_cell(item.get("evidence", {})),
    }


def _json_cell(value: Any) -> str:
    return json.dumps(value if isinstance(value, dict) else {}, sort_keys=True)


def _load_sql() -> str:
    return """create schema if not exists civic_wave1;

create table if not exists civic_wave1.ward (
  ward_key text primary key,
  source_id text,
  ward_number text,
  ward_name text not null,
  normalized_name text not null,
  version text not null,
  zone text,
  corporation text,
  assembly_constituency text,
  population integer,
  evidence_json jsonb not null
);

create table if not exists civic_wave1.old_new_ward_mapping (
  old_ward_number text,
  old_ward_name text,
  new_ward_number text,
  new_ward_name text not null,
  assembly_constituency text,
  parliamentary_constituency text,
  confidence numeric not null,
  method text not null,
  explanation text,
  evidence_json jsonb not null
);

create table if not exists civic_wave1.issue_category (
  name text primary key,
  normalized_name text not null,
  source text not null
);

create table if not exists civic_wave1.complaint (
  external_complaint_id text primary key,
  issue_category text,
  issue_subcategory text,
  grievance_date date,
  year integer,
  ward_name_raw text,
  normalized_ward_name text,
  status text,
  staff_remarks text,
  staff_name text,
  evidence_json jsonb not null
);

truncate civic_wave1.complaint;
truncate civic_wave1.issue_category;
truncate civic_wave1.old_new_ward_mapping;
truncate civic_wave1.ward;

\\copy civic_wave1.ward from 'ward.csv' with (format csv, header true)
\\copy civic_wave1.old_new_ward_mapping from 'old_new_ward_mapping.csv' with (format csv, header true)
\\copy civic_wave1.issue_category from 'issue_category.csv' with (format csv, header true)
\\copy civic_wave1.complaint from 'complaint.csv' with (format csv, header true)
"""
