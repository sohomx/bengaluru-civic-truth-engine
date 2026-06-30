from __future__ import annotations

import csv
import json
import re
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any


WARD_SOURCES = {
    "bbmp_ward_information",
    "gba_wards_delimitation_2025",
    "bbmp_ward_wise_public_goods_data",
    "bengaluru_bbmp_ward_details",
}
GRIEVANCE_SOURCES = {"bbmp_grievances_data"}


def normalize_wards(raw_root: Path, warehouse_root: Path) -> dict[str, int]:
    warehouse_root.mkdir(parents=True, exist_ok=True)
    wards: dict[str, dict[str, Any]] = {}
    mappings: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    for source_id in sorted(WARD_SOURCES):
        run_dir = latest_successful_run(raw_root / source_id)
        if run_dir is None:
            continue
        for file_path in _manifest_csv_files(run_dir):
            for row_number, row in _read_csv_rows(file_path):
                try:
                    if _is_old_new_mapping(row):
                        mappings.append(_mapping_record(source_id, run_dir, file_path, row_number, row))
                    ward = _ward_record(source_id, run_dir, file_path, row_number, row)
                    if ward:
                        wards.setdefault(str(ward["ward_key"]), ward)
                except ValueError as exc:
                    rejected.append(_rejection(source_id, file_path, row_number, str(exc), row))

    _write_json(warehouse_root / "wards.json", sorted(wards.values(), key=_ward_sort_key))
    _write_json(warehouse_root / "old_new_ward_mappings.json", mappings)
    _write_json(warehouse_root / "ward_rejections.json", rejected)
    return {"wards": len(wards), "old_new_ward_mappings": len(mappings), "rejected": len(rejected)}


def normalize_grievances(raw_root: Path, warehouse_root: Path) -> dict[str, int]:
    warehouse_root.mkdir(parents=True, exist_ok=True)
    complaints: dict[str, dict[str, Any]] = {}
    categories: dict[str, dict[str, Any]] = {}
    rejected: list[dict[str, Any]] = []

    for source_id in sorted(GRIEVANCE_SOURCES):
        run_dir = latest_successful_run(raw_root / source_id)
        if run_dir is None:
            continue
        for file_path in _manifest_csv_files(run_dir):
            for row_number, row in _read_csv_rows(file_path):
                try:
                    complaint = _complaint_record(source_id, run_dir, file_path, row_number, row)
                    complaints.setdefault(str(complaint["external_complaint_id"]), complaint)
                    category = str(complaint["issue_category"])
                    if category:
                        categories.setdefault(
                            category,
                            {
                                "name": category,
                                "normalized_name": normalize_name(category),
                                "source": "observed_grievance_category",
                            },
                        )
                except ValueError as exc:
                    rejected.append(_rejection(source_id, file_path, row_number, str(exc), row))

    _write_json(
        warehouse_root / "complaints.json",
        sorted(complaints.values(), key=lambda item: str(item.get("external_complaint_id", ""))),
    )
    _write_json(
        warehouse_root / "issue_categories.json",
        sorted(categories.values(), key=lambda item: str(item.get("normalized_name", ""))),
    )
    _write_json(warehouse_root / "complaint_rejections.json", rejected)
    return {
        "complaints": len(complaints),
        "issue_categories": len(categories),
        "rejected": len(rejected),
    }


def latest_successful_run(source_dir: Path) -> Path | None:
    if not source_dir.exists():
        return None
    for run_dir in sorted([path for path in source_dir.iterdir() if path.is_dir()], reverse=True):
        manifest_path = run_dir / "manifest.json"
        if not manifest_path.exists():
            continue
        try:
            manifest = json.loads(manifest_path.read_text())
        except json.JSONDecodeError:
            continue
        if manifest.get("status") == "success":
            return run_dir
    return None


def normalize_name(value: str) -> str:
    text = value.strip().lower()
    text = re.sub(r"\bward\b", "", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def _manifest_csv_files(run_dir: Path) -> list[Path]:
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.exists():
        return []
    try:
        manifest = json.loads(manifest_path.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid manifest JSON: {manifest_path}") from exc
    files = manifest.get("files", [])
    if not isinstance(files, list):
        raise ValueError(f"Manifest files must be a list: {manifest_path}")
    paths: list[Path] = []
    for item in files:
        if not isinstance(item, dict):
            continue
        relative = item.get("path")
        if not isinstance(relative, str):
            continue
        path = run_dir / relative
        if path.suffix.lower() == ".csv" and path.exists():
            paths.append(path)
    return paths


def _read_csv_rows(path: Path) -> Iterable[tuple[int, dict[str, str]]]:
    try:
        handle = path.open(newline="", encoding="utf-8-sig")
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            handle.close()
            return
        with handle:
            for row_number, row in enumerate(reader, start=2):
                yield row_number, {str(key): str(value or "") for key, value in row.items() if key is not None}
    except UnicodeDecodeError:
        with path.open(newline="", encoding="latin-1") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames:
                return
            for row_number, row in enumerate(reader, start=2):
                yield row_number, {str(key): str(value or "") for key, value in row.items() if key is not None}


def _is_old_new_mapping(row: dict[str, str]) -> bool:
    return "Old Ward Num" in row and "New Ward Num" in row


def _mapping_record(
    source_id: str, run_dir: Path, file_path: Path, row_number: int, row: dict[str, str]
) -> dict[str, Any]:
    old_number = row.get("Old Ward Num", "").strip()
    old_name = row.get("Old Ward Name", "").strip()
    new_number = row.get("New Ward Num", "").strip()
    new_name = row.get("New Ward Name", "").strip()
    if not new_number or not new_name:
        raise ValueError("mapping row missing new ward number or name")
    return {
        "old_ward_number": old_number,
        "old_ward_name": old_name,
        "new_ward_number": new_number,
        "new_ward_name": new_name,
        "assembly_constituency": row.get("AC Name", "").strip(),
        "parliamentary_constituency": row.get("Parliamentary Constituency Name", "").strip(),
        "confidence": 1.0,
        "method": "official_mapping_csv",
        "explanation": "Official source row directly maps old ward fields to new ward fields.",
        "evidence": _evidence(source_id, run_dir, file_path, row_number),
    }


def _ward_record(
    source_id: str, run_dir: Path, file_path: Path, row_number: int, row: dict[str, str]
) -> dict[str, Any] | None:
    if "Complaint ID" in row:
        return None
    if "Ward_No_Name" in row:
        ward_number, ward_name = _split_ward_no_name(row.get("Ward_No_Name", ""))
        if not ward_number or not ward_name:
            raise ValueError("GBA row missing Ward_No_Name")
        version = "gba_2025"
        corporation = row.get("Corporation_Name", "").strip()
        ward_key = f"gba:{normalize_name(corporation) or 'unknown'}:{ward_number}"
        return {
            "ward_key": ward_key,
            "source_id": source_id,
            "ward_number": ward_number,
            "ward_name": ward_name,
            "normalized_name": normalize_name(ward_name),
            "version": version,
            "zone": "",
            "corporation": corporation,
            "assembly_constituency": row.get("Assembly_Name", "").strip(),
            "population": _int_or_none(row.get("TOT_P", "")),
            "evidence": _evidence(source_id, run_dir, file_path, row_number),
        }

    ward_number = (
        row.get("Ward No")
        or row.get("Ward_No")
        or row.get("Ward No.")
        or row.get("ward number")
        or row.get("Ward")
        or ""
    ).strip()
    ward_name = (
        row.get("Ward Name")
        or row.get("Ward Names")
        or row.get("name_en")
        or row.get("Old Ward Name")
        or row.get("New Ward Name")
        or ""
    ).strip()
    if not ward_number or not ward_name:
        return None
    return {
        "ward_key": f"old:{ward_number}",
        "source_id": source_id,
        "ward_number": ward_number,
        "ward_name": ward_name,
        "normalized_name": normalize_name(ward_name),
        "version": "old_bbmp",
        "zone": (row.get("BBMP Zone Name") or row.get("Zones") or "").strip(),
        "corporation": "",
        "assembly_constituency": (
            row.get("Assembly constituency")
            or row.get("Assembly Constituency")
            or row.get("Assembly Constituency Name")
            or ""
        ).strip(),
        "population": _int_or_none(row.get("Population (2011)", "") or row.get("Total Population", "")),
        "evidence": _evidence(source_id, run_dir, file_path, row_number),
    }


def _complaint_record(
    source_id: str, run_dir: Path, file_path: Path, row_number: int, row: dict[str, str]
) -> dict[str, Any]:
    complaint_id = row.get("Complaint ID", "").strip()
    if not complaint_id:
        raise ValueError("complaint row missing Complaint ID")
    ward_name = row.get("Ward Name", "").strip()
    if not ward_name:
        raise ValueError(f"complaint {complaint_id} missing Ward Name")
    date_text = row.get("Grievance Date", "").strip()
    grievance_date = _parse_date(date_text)
    category = row.get("Category", "").strip()
    subcategory = row.get("Sub Category", "").strip()
    return {
        "external_complaint_id": complaint_id,
        "issue_category": category,
        "issue_subcategory": subcategory,
        "grievance_date": grievance_date,
        "year": int(grievance_date[:4]) if grievance_date else None,
        "ward_name_raw": ward_name,
        "normalized_ward_name": normalize_name(ward_name),
        "status": row.get("Grievance Status", "").strip(),
        "staff_remarks": row.get("Staff Remarks", "").strip(),
        "staff_name": row.get("Staff Name", "").strip(),
        "evidence": _evidence(source_id, run_dir, file_path, row_number),
    }


def _split_ward_no_name(value: str) -> tuple[str, str]:
    text = value.strip()
    if not text:
        return "", ""
    match = re.match(r"^(\d+)\s*[-:]\s*(.+)$", text)
    if match:
        return match.group(1).strip(), match.group(2).strip()
    return "", text


def _parse_date(value: str) -> str:
    if not value:
        return ""
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(value[:26], fmt).date().isoformat()
        except ValueError:
            continue
    if re.match(r"^\d{4}-\d{2}-\d{2}", value):
        return value[:10]
    raise ValueError(f"invalid Grievance Date: {value}")


def _int_or_none(value: str) -> int | None:
    cleaned = str(value).replace(",", "").strip()
    if not cleaned:
        return None
    try:
        return int(float(cleaned))
    except ValueError:
        return None


def _evidence(source_id: str, run_dir: Path, file_path: Path, row_number: int) -> dict[str, Any]:
    return {
        "source_id": source_id,
        "run_id": run_dir.name,
        "raw_file": str(file_path.relative_to(run_dir)),
        "row_number": row_number,
    }


def _rejection(
    source_id: str, file_path: Path, row_number: int, reason: str, row: dict[str, str]
) -> dict[str, Any]:
    return {
        "source_id": source_id,
        "raw_file": str(file_path),
        "row_number": row_number,
        "reason": reason,
        "row": row,
    }


def _ward_sort_key(item: dict[str, Any]) -> tuple[str, int, str]:
    number = str(item.get("ward_number", ""))
    return (
        str(item.get("version", "")),
        int(number) if number.isdigit() else 99999,
        str(item.get("ward_name", "")),
    )


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True))
