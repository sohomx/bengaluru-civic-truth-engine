from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


def profile_archives(
    sources: list[dict[str, Any]], raw_root: Path, export_root: Path
) -> list[dict[str, str]]:
    export_root.mkdir(parents=True, exist_ok=True)
    rows = [_profile_source(source, raw_root) for source in sources]
    _write_csv(export_root / "parser_backlog.csv", rows)
    _write_csv(export_root / "source_inventory.csv", rows)
    _write_csv(
        export_root / "fetch_status.csv",
        [
            {
                "source_id": row["source_id"],
                "fetched_status": row["fetched_status"],
                "file_count": row["file_count"],
                "expected_resource_count": row["expected_resource_count"],
                "fetched_resource_count": row["fetched_resource_count"],
                "failed_resource_count": row["failed_resource_count"],
                "pending_resource_count": row["pending_resource_count"],
                "total_bytes": row["total_bytes"],
                "blocking_issues": row["blocking_issues"],
            }
            for row in rows
        ],
    )
    return rows


def _profile_source(source: dict[str, Any], raw_root: Path) -> dict[str, str]:
    source_id = str(source["id"])
    run_dir = _latest_run_dir(raw_root / source_id)
    if run_dir is None:
        return _empty_profile(source, "not_fetched", "No archive run found")

    manifest_path = run_dir / "manifest.json"
    if not manifest_path.exists():
        return _empty_profile(source, "failed", "Missing manifest.json")
    manifest = json.loads(manifest_path.read_text())
    files = manifest.get("files", [])
    if not isinstance(files, list):
        files = []
    resource_counts = _resource_counts(manifest, run_dir)
    total_bytes = sum(int(item.get("bytes", 0)) for item in files if isinstance(item, dict))
    detected_columns = ""
    row_count = ""
    geometry_detected = "false"
    pdf_page_count = ""
    parser_difficulty = _difficulty_for_source(source)
    issues = "; ".join(str(error) for error in manifest.get("errors", []))

    for item in files:
        if not isinstance(item, dict):
            continue
        path = run_dir / str(item.get("path", ""))
        suffix = path.suffix.lower()
        if suffix == ".csv" and not detected_columns:
            detected_columns, row_count = _profile_csv(path)
            parser_difficulty = "easy_structured"
        elif suffix in {".kml", ".geojson", ".json"} and not geometry_detected == "true":
            geometry_detected = _detect_geometry(path)
            if geometry_detected == "true":
                parser_difficulty = "geo_structured"
        elif suffix == ".pdf" and not pdf_page_count:
            pdf_page_count = _count_pdf_pages(path)
            parser_difficulty = "pdf_extract"

    return {
        "source_id": source_id,
        "domain": str(source.get("domain", "")),
        "format": str(source.get("format", "")),
        "fetched_status": str(manifest.get("status", "unknown")),
        "file_count": str(len(files)),
        "expected_resource_count": str(resource_counts["expected"]),
        "fetched_resource_count": str(resource_counts["fetched"]),
        "failed_resource_count": str(resource_counts["failed"]),
        "pending_resource_count": str(resource_counts["pending"]),
        "total_bytes": str(total_bytes),
        "detected_columns": detected_columns,
        "row_count_if_tabular": row_count,
        "geometry_detected": geometry_detected,
        "pdf_page_count_if_pdf": pdf_page_count,
        "parser_difficulty": parser_difficulty,
        "normalization_wave": str(_normalization_wave(source)),
        "blocking_issues": issues,
    }


def _empty_profile(source: dict[str, Any], status: str, issue: str) -> dict[str, str]:
    return {
        "source_id": str(source["id"]),
        "domain": str(source.get("domain", "")),
        "format": str(source.get("format", "")),
        "fetched_status": status,
        "file_count": "0",
        "expected_resource_count": "0",
        "fetched_resource_count": "0",
        "failed_resource_count": "0",
        "pending_resource_count": "0",
        "total_bytes": "0",
        "detected_columns": "",
        "row_count_if_tabular": "",
        "geometry_detected": "false",
        "pdf_page_count_if_pdf": "",
        "parser_difficulty": _difficulty_for_source(source),
        "normalization_wave": str(_normalization_wave(source)),
        "blocking_issues": issue,
    }


def _latest_run_dir(source_dir: Path) -> Path | None:
    if not source_dir.exists():
        return None
    dirs = [path for path in source_dir.iterdir() if path.is_dir()]
    return sorted(dirs)[-1] if dirs else None


def _resource_counts(manifest: dict[str, Any], run_dir: Path) -> dict[str, int]:
    summary = manifest.get("ckan_resources")
    if not isinstance(summary, dict):
        return _infer_v1_ckan_resource_counts(manifest, run_dir)
    return {
        "expected": int(summary.get("total", 0) or 0),
        "fetched": int(summary.get("completed", 0) or 0),
        "failed": int(summary.get("failed", 0) or 0),
        "pending": int(summary.get("pending", 0) or 0),
    }


def _infer_v1_ckan_resource_counts(
    manifest: dict[str, Any], run_dir: Path
) -> dict[str, int]:
    package_path = run_dir / "original" / "ckan_package.json"
    if not package_path.exists():
        return {"expected": 0, "fetched": 0, "failed": 0, "pending": 0}
    try:
        package = json.loads(package_path.read_text())
    except json.JSONDecodeError:
        return {"expected": 0, "fetched": 0, "failed": 0, "pending": 0}
    resources = package.get("result", {}).get("resources", [])
    if not isinstance(resources, list):
        return {"expected": 0, "fetched": 0, "failed": 0, "pending": 0}
    expected_ids = {
        str(resource.get("id"))
        for resource in resources
        if isinstance(resource, dict)
        and resource.get("state") in (None, "active")
        and resource.get("id")
    }
    files = manifest.get("files", [])
    fetched_ids = set()
    if isinstance(files, list):
        for item in files:
            if not isinstance(item, dict):
                continue
            stem = Path(str(item.get("path", ""))).stem
            if stem in expected_ids:
                fetched_ids.add(stem)
    expected = len(expected_ids)
    fetched = len(fetched_ids)
    failed = 0 if manifest.get("status") == "success" else max(expected - fetched, 0)
    return {
        "expected": expected,
        "fetched": fetched if fetched else (expected if manifest.get("status") == "success" else 0),
        "failed": failed,
        "pending": max(expected - fetched - failed, 0),
    }


def _profile_csv(path: Path) -> tuple[str, str]:
    try:
        with path.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.reader(handle)
            header = next(reader, [])
            count = sum(1 for _ in reader)
    except UnicodeDecodeError:
        with path.open(newline="", encoding="latin-1") as handle:
            reader = csv.reader(handle)
            header = next(reader, [])
            count = sum(1 for _ in reader)
    return "|".join(header), str(count)


def _detect_geometry(path: Path) -> str:
    try:
        text = path.read_text(errors="ignore")[:20000].lower()
    except OSError:
        return "false"
    return "true" if any(token in text for token in ("<coordinates", '"coordinates"', '"geometry"')) else "false"


def _count_pdf_pages(path: Path) -> str:
    try:
        data = path.read_bytes()
    except OSError:
        return ""
    return str(data.count(b"/Type /Page"))


def _difficulty_for_source(source: dict[str, Any]) -> str:
    access_method = source.get("access_method")
    fmt = str(source.get("format", "")).lower()
    official_status = source.get("official_status")
    if access_method == "official_portal_scrape_later":
        return "portal_later"
    if official_status in {"community_signal", "external_reference", "unofficial"}:
        return "community_signal_only"
    if "pdf" in fmt:
        return "pdf_extract"
    if "kml" in fmt or "gis" in fmt or "geo" in fmt:
        return "geo_structured"
    if "csv" in fmt or "ckan" in fmt:
        return "medium_structured"
    if "html" in fmt:
        return "html_snapshot_only"
    return "manual_review"


def _normalization_wave(source: dict[str, Any]) -> int:
    domain = source.get("domain")
    if domain == "wards":
        return 1
    if domain == "grievances":
        return 2
    if domain == "works_payments_tenders":
        return 3
    if domain in {"roads", "stormwater_flooding", "swm", "streetlights"}:
        return 4
    if domain in {"rules", "budgets_governance"}:
        return 5
    if domain in {"water_sewage", "traffic_mobility"}:
        return 6
    return 7


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    if not rows:
        path.write_text("")
        return
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
