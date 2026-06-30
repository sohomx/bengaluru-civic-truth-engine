from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from civic_data.normalize import normalize_name


def build_place_truth(
    query: str,
    warehouse_root: Path,
    year_from: int | None = None,
    year_to: int | None = None,
    lens_label: str | None = None,
) -> dict[str, Any]:
    q = query.strip()
    if not q:
        raise ValueError("--q must not be empty")
    if year_from is not None and year_to is not None and year_from > year_to:
        raise ValueError("--year-from must be less than or equal to --year-to")
    normalized_query = normalize_name(q)
    wards = _read_json_list(warehouse_root / "wards.json")
    mappings = _read_json_list(warehouse_root / "old_new_ward_mappings.json")
    complaints = _read_json_list(warehouse_root / "complaints.json")

    matching_wards = [_with_match_score(ward, normalized_query) for ward in wards]
    matching_wards = [ward for ward in matching_wards if ward["match_score"] > 0]
    old_candidates = sorted(
        [ward for ward in matching_wards if ward.get("version") == "old_bbmp"],
        key=lambda item: (-float(item["match_score"]), str(item.get("ward_name", ""))),
    )
    new_candidates = sorted(
        [ward for ward in matching_wards if ward.get("version") == "gba_2025"],
        key=lambda item: (-float(item["match_score"]), str(item.get("ward_name", ""))),
    )
    area_candidates = sorted(
        [_with_area_match_score(ward, normalized_query) for ward in wards],
        key=lambda item: (-float(item["match_score"]), str(item.get("ward_name", ""))),
    )
    area_candidates = [ward for ward in area_candidates if ward["match_score"] > 0]

    mapped_old_candidates = _mapped_old_candidates(normalized_query, mappings, wards)
    for candidate in mapped_old_candidates:
        key = (candidate.get("ward_number"), candidate.get("ward_name"))
        if not any((item.get("ward_number"), item.get("ward_name")) == key for item in old_candidates):
            old_candidates.append(candidate)

    relevant_names = {normalized_query}
    relevant_names.update(
        str(ward.get("normalized_name", ""))
        for ward in old_candidates + new_candidates + area_candidates
    )
    relevant_names.update(normalize_name(str(item.get("old_ward_name", ""))) for item in mappings if _mapping_matches(item, normalized_query))
    relevant_names.update(normalize_name(str(item.get("new_ward_name", ""))) for item in mappings if _mapping_matches(item, normalized_query))
    matching_complaints = [
        complaint
        for complaint in complaints
        if str(complaint.get("normalized_ward_name", "")) in relevant_names
    ]
    record_scope = _record_scope(
        all_matching_complaints=matching_complaints,
        year_from=year_from,
        year_to=year_to,
        lens_label=lens_label,
    )
    matching_complaints = [
        complaint
        for complaint in matching_complaints
        if _complaint_in_year_range(complaint, year_from, year_to)
    ]

    by_year = Counter(str(item.get("year")) for item in matching_complaints if item.get("year"))
    by_status = Counter(str(item.get("status", "")) for item in matching_complaints if item.get("status"))
    by_category = Counter(str(item.get("issue_category", "")) for item in matching_complaints if item.get("issue_category"))
    examples_by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for complaint in matching_complaints:
        category = str(complaint.get("issue_category", ""))
        if category and len(examples_by_category[category]) < 3:
            examples_by_category[category].append(_complaint_example(complaint))

    return {
        "query": q,
        "normalized_query": normalized_query,
        "record_scope": record_scope,
        "ward_context": {
            "old_bbmp_candidates": old_candidates[:10],
            "new_gba_candidates": new_candidates[:10],
            "area_match_candidates": area_candidates[:25],
            "old_new_mappings": [
                item for item in mappings if _mapping_matches(item, normalized_query)
            ][:10],
        },
        "complaint_summary": {
            "total_complaints": len(matching_complaints),
            "by_year": _counter_rows(by_year),
            "by_status": _counter_rows(by_status),
        },
        "top_issue_categories": [
            {
                "category": category,
                "count": count,
                "examples": examples_by_category.get(category, []),
            }
            for category, count in by_category.most_common(10)
        ],
        "evidence_policy": "All claims in this report are derived from normalized rows with evidence pointers. Community signals are not included in this Wave 1 report.",
    }


def write_place_truth(
    query: str,
    warehouse_root: Path,
    output_path: Path | None,
    year_from: int | None = None,
    year_to: int | None = None,
    lens_label: str | None = None,
) -> dict[str, Any]:
    truth = build_place_truth(
        query=query,
        warehouse_root=warehouse_root,
        year_from=year_from,
        year_to=year_to,
        lens_label=lens_label,
    )
    text = json.dumps(truth, indent=2, sort_keys=True)
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text)
    else:
        print(text)
    return truth


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


def _with_match_score(ward: dict[str, Any], normalized_query: str) -> dict[str, Any]:
    name = str(ward.get("normalized_name", ""))
    score = 0.0
    if name == normalized_query:
        score = 1.0
    elif normalized_query and normalized_query in name:
        score = 0.85
    elif name and name in normalized_query:
        score = 0.75
    item = dict(ward)
    item["match_score"] = score
    return item


def _with_area_match_score(ward: dict[str, Any], normalized_query: str) -> dict[str, Any]:
    fields = [
        str(ward.get("zone", "")),
        str(ward.get("corporation", "")),
        str(ward.get("assembly_constituency", "")),
    ]
    score = 0.0
    match_field = ""
    for field in fields:
        normalized = normalize_name(field)
        if not normalized:
            continue
        if normalized == normalized_query:
            score = max(score, 0.7)
            match_field = field
        elif normalized_query in normalized or normalized in normalized_query:
            score = max(score, 0.55)
            match_field = field
    item = dict(ward)
    item["match_score"] = score
    if match_field:
        item["match_method"] = "area_context"
        item["matched_area_context"] = match_field
    return item


def _mapped_old_candidates(
    normalized_query: str, mappings: list[dict[str, Any]], wards: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    old_by_number = {
        str(item.get("ward_number")): item
        for item in wards
        if item.get("version") == "old_bbmp" and item.get("ward_number")
    }
    candidates = []
    for mapping in mappings:
        if normalize_name(str(mapping.get("new_ward_name", ""))) != normalized_query:
            continue
        old_number = str(mapping.get("old_ward_number", ""))
        old_name = str(mapping.get("old_ward_name", ""))
        if not old_number.strip() and not old_name.strip():
            continue
        old = old_by_number.get(old_number)
        if old:
            item = dict(old)
        else:
            item = {
                "ward_key": f"old:{old_number}",
                "ward_number": old_number,
                "ward_name": old_name,
                "normalized_name": normalize_name(old_name),
                "version": "old_bbmp",
                "zone": "",
                "corporation": "",
                "evidence": mapping.get("evidence", {}),
            }
        item["match_score"] = float(mapping.get("confidence", 0.0) or 0.0)
        item["match_method"] = "official_old_new_mapping"
        candidates.append(item)
    return candidates


def _mapping_matches(mapping: dict[str, Any], normalized_query: str) -> bool:
    names = {
        normalize_name(str(mapping.get("old_ward_name", ""))),
        normalize_name(str(mapping.get("new_ward_name", ""))),
    }
    return normalized_query in names


def _counter_rows(counter: Counter[str]) -> list[dict[str, Any]]:
    return [{"value": value, "count": count} for value, count in counter.most_common()]


def _complaint_in_year_range(
    complaint: dict[str, Any], year_from: int | None, year_to: int | None
) -> bool:
    if year_from is None and year_to is None:
        return True
    year = _as_int(complaint.get("year"))
    if year is None:
        return False
    if year_from is not None and year < year_from:
        return False
    if year_to is not None and year > year_to:
        return False
    return True


def _record_scope(
    all_matching_complaints: list[dict[str, Any]],
    year_from: int | None,
    year_to: int | None,
    lens_label: str | None,
) -> dict[str, Any]:
    years = sorted(
        year
        for year in (_as_int(item.get("year")) for item in all_matching_complaints)
        if year is not None
    )
    dates = sorted(
        date
        for date in (str(item.get("grievance_date", "")).strip() for item in all_matching_complaints)
        if date
    )
    date_max = dates[-1] if dates else None
    if lens_label and lens_label.strip():
        label = lens_label.strip()
    elif year_from is None and year_to is None:
        label = "All years"
    elif year_from == year_to:
        label = f"{year_from} only"
    elif year_from is None:
        label = f"Through {year_to}"
    elif year_to is None:
        label = f"From {year_from}"
    else:
        label = f"{year_from}-{year_to}"
    freshness_prefix = (
        f"BBMP grievance records available through {date_max}."
        if date_max
        else "BBMP grievance record freshness is unavailable."
    )
    return {
        "label": label,
        "grievance_year_min": years[0] if years else None,
        "grievance_year_max": years[-1] if years else None,
        "grievance_date_min": dates[0] if dates else None,
        "grievance_date_max": date_max,
        "active_year_from": year_from,
        "active_year_to": year_to,
        "freshness_note": f"{freshness_prefix} Not a live complaint dashboard.",
        "context_note": "2026 sources are present for ward/governance/budget context, not grievance trends yet.",
    }


def _as_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _complaint_example(complaint: dict[str, Any]) -> dict[str, Any]:
    return {
        "external_complaint_id": complaint.get("external_complaint_id"),
        "issue_subcategory": complaint.get("issue_subcategory"),
        "grievance_date": complaint.get("grievance_date"),
        "status": complaint.get("status"),
        "staff_name": complaint.get("staff_name"),
        "staff_remarks": complaint.get("staff_remarks"),
        "evidence": complaint.get("evidence", {}),
    }
