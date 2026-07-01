from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from civic_data import __version__
from civic_data.dossier import render_dossier
from civic_data.profile import profile_archives
from civic_data.registry import load_sources, registry_hash, validate_registry
from civic_data.source_monitor import build_source_monitor_report
from civic_data.truth import build_place_truth


DEFAULT_PLACES = [
    ("Bellandur", "bellandur"),
    ("Mahadevapura", "mahadevapura"),
    ("Varthur", "varthur"),
    ("Whitefield", "whitefield"),
]

LENSES = [
    ("all", None, None, "All years"),
    ("recent", 2024, 2025, "Recent: 2024-2025"),
    ("y2025", 2025, 2025, "2025 only"),
]


@dataclass(frozen=True)
class SiteBuildResult:
    generated_at: str
    truth_payloads: int
    source_count: int
    known_gaps: list[str]


def build_site_data(
    registry_path: Path,
    schema_path: Path,
    raw_root: Path,
    warehouse_root: Path,
    web_data_root: Path,
    dossier_root: Path,
    places: list[tuple[str, str]] | None = None,
) -> SiteBuildResult:
    sources = load_sources(registry_path)
    errors = validate_registry(sources, schema_path)
    if errors:
        raise ValueError("Registry validation failed: " + "; ".join(errors))

    generated_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    snapshot_id = registry_hash(registry_path)
    selected_places = places or DEFAULT_PLACES
    web_data_root.mkdir(parents=True, exist_ok=True)
    dossier_root.mkdir(parents=True, exist_ok=True)

    profiles = profile_archives(sources=sources, raw_root=raw_root, export_root=web_data_root / "profile")
    source_status_rows = build_source_monitor_report(sources, raw_root, profiles=profiles)["sources"]

    payload_count = 0
    all_known_gaps = _source_known_gaps(source_status_rows)
    place_summaries = []
    search_entries: list[dict[str, Any]] = []
    used_sources: set[str] = set()

    for place_name, slug in selected_places:
        place_dir = web_data_root / "truth" / slug
        place_dir.mkdir(parents=True, exist_ok=True)
        lens_summaries = []
        all_payload: dict[str, Any] | None = None
        for lens_key, year_from, year_to, lens_label in LENSES:
            payload = build_place_truth(
                query=place_name,
                warehouse_root=warehouse_root,
                year_from=year_from,
                year_to=year_to,
                lens_label=lens_label,
            )
            if lens_key == "all":
                all_payload = payload
            claim_cards = _claim_cards(payload)
            source_ids = sorted(_payload_source_ids(payload))
            used_sources.update(source_ids)
            known_gaps = _payload_known_gaps(place_name, payload)
            enriched = dict(payload)
            enriched["build_metadata"] = {
                "generated_at": generated_at,
                "code_version": __version__,
                "source_snapshot_id": snapshot_id,
                "included_sources": source_ids,
                "excluded_sources": sorted(
                    str(source.get("id", "")) for source in sources if str(source.get("id", "")) not in source_ids
                ),
                "record_date_min": payload.get("record_scope", {}).get("grievance_date_min"),
                "record_date_max": payload.get("record_scope", {}).get("grievance_date_max"),
                "known_gaps": known_gaps,
            }
            enriched["claim_cards"] = claim_cards
            _write_json(place_dir / f"{lens_key}.json", enriched)
            payload_count += 1
            all_known_gaps.extend(known_gaps)
            lens_summaries.append(
                {
                    "key": lens_key,
                    "label": lens_label,
                    "total_complaints": payload.get("complaint_summary", {}).get("total_complaints", 0),
                    "record_date_max": payload.get("record_scope", {}).get("grievance_date_max"),
                }
            )
        if all_payload is not None:
            dossier_text = render_dossier(all_payload)
            (dossier_root / f"dossier-{slug}.md").write_text(dossier_text)
            web_dossier_dir = web_data_root / "dossiers"
            web_dossier_dir.mkdir(parents=True, exist_ok=True)
            (web_dossier_dir / f"{slug}.md").write_text(dossier_text)
            search_entries.append(_place_search_entry(place_name, slug, all_payload))
        place_summaries.append({"name": place_name, "slug": slug, "lenses": lens_summaries})

    source_monitor = build_source_monitor_report(sources, raw_root, profiles=profiles, used_sources=used_sources)
    source_status = {
        "generated_at": generated_at,
        "source_snapshot_id": snapshot_id,
        "summary": source_monitor["summary"],
        "sources": sorted(source_monitor["sources"], key=lambda item: item["source_id"]),
    }
    _write_json(web_data_root / "source_status.json", source_status)
    _write_json(web_data_root / "places.json", {"generated_at": generated_at, "places": place_summaries})
    search_entries.extend(_source_search_entries(source_status["sources"]))
    _write_json(
        web_data_root / "search_index.json",
        {
            "generated_at": generated_at,
            "source_snapshot_id": snapshot_id,
            "entries": search_entries,
        },
    )
    deduped_gaps = sorted(set(all_known_gaps))
    report = {
        "generated_at": generated_at,
        "code_version": __version__,
        "source_snapshot_id": snapshot_id,
        "counts": {
            "sources": len(sources),
            "truth_payloads": payload_count,
            "pilot_places": len(selected_places),
            "known_gaps": len(deduped_gaps),
        },
        "known_gaps": deduped_gaps,
        "warnings": _build_warnings(selected_places, web_data_root),
    }
    _write_json(web_data_root / "build_report.json", report)
    return SiteBuildResult(
        generated_at=generated_at,
        truth_payloads=payload_count,
        source_count=len(sources),
        known_gaps=deduped_gaps,
    )


def parse_place_arg(value: str) -> tuple[str, str]:
    parts = value.split(":", 1)
    name = parts[0].strip()
    if not name:
        raise ValueError("--place must include a non-empty place name")
    slug = parts[1].strip() if len(parts) == 2 else _slugify(name)
    if not slug:
        raise ValueError("--place slug must not be empty")
    return name, slug


def _claim_cards(payload: dict[str, Any]) -> list[dict[str, Any]]:
    total = int(payload.get("complaint_summary", {}).get("total_complaints", 0) or 0)
    record_scope = payload.get("record_scope", {})
    citations = _example_citations(payload)
    cards = [
        {
            "claim": (
                f"Official grievance records show {total} complaints connected to "
                f"{payload.get('query', 'this place')} in this lens."
            ),
            "claim_level": "official_records_show",
            "time_range": _time_range(record_scope),
            "confidence": "high" if citations else "medium",
            "citations": citations,
            "caveat": "Complaint volume reflects available official records, not total ground reality.",
        }
    ]
    top_issue = (payload.get("top_issue_categories") or [{}])[0]
    if top_issue.get("category"):
        cards.append(
            {
                "claim": (
                    f"{top_issue['category']} is the top recurring issue category in "
                    f"the available grievance records."
                ),
                "claim_level": "available_data_suggests",
                "time_range": _time_range(record_scope),
                "confidence": "medium",
                "citations": _issue_citations(top_issue),
                "caveat": "Ranking is based on source categories and may reflect reporting behavior.",
            }
        )
    return cards


def _place_search_entry(place_name: str, slug: str, payload: dict[str, Any]) -> dict[str, Any]:
    top_issues = [
        {"category": issue.get("category"), "count": issue.get("count", 0)}
        for issue in payload.get("top_issue_categories", [])[:5]
        if issue.get("category")
    ]
    total = int(payload.get("complaint_summary", {}).get("total_complaints", 0) or 0)
    record_scope = payload.get("record_scope", {})
    return {
        "id": slug,
        "kind": "place",
        "answer_focus": "place_memory",
        "title": place_name,
        "href": f"/places/{slug}",
        "summary": (
            f"Official grievance records show {total} complaints connected to {place_name}. "
            f"Latest available grievance record: {record_scope.get('grievance_date_max') or 'unavailable'}."
        ),
        "keywords": sorted(
            {
                place_name.lower(),
                slug,
                *(str(issue["category"]).lower() for issue in top_issues),
            }
        ),
        "freshness_note": record_scope.get("freshness_note", ""),
        "record_date_max": record_scope.get("grievance_date_max"),
        "total_complaints": total,
        "top_issues": top_issues,
        "claim_cards": _claim_cards(payload),
        "retrieval_note": "Use this place record to connect issue recurrence, ward context, claim cards, and citations.",
    }


def _source_search_entries(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    entries = []
    for source in sources:
        answer_focus = _source_answer_focus(source)
        entries.append(
            {
                "id": source["source_id"],
                "kind": "source",
                "answer_focus": answer_focus,
                "title": source["name"],
                "href": f"/sources/{source['source_id']}",
                "summary": (
                    f"{source['publisher']} source in {source['domain']} with "
                    f"{source['latest_fetch_status']} fetch status and {source['parser_status']} parser status."
                ),
                "keywords": _source_query_keywords(source, answer_focus),
                "freshness_note": source["freshness_label"],
                "record_date_max": source["latest_fetched_at"],
                "total_complaints": None,
                "top_issues": [],
                "claim_cards": [],
                "retrieval_note": _source_retrieval_note(source, answer_focus),
            }
        )
    return entries


def _source_answer_focus(source: dict[str, Any]) -> str:
    domain = str(source.get("domain", "")).lower()
    source_id = str(source.get("source_id", "")).lower()
    if domain == "works_payments_tenders" or any(
        token in source_id for token in ("tender", "work_order", "payment", "bill", "contractor")
    ):
        return "money_trail"
    if domain == "budgets_governance" or "budget" in source_id:
        return "budget_context"
    if domain == "grievances" or "grievance" in source_id or "complaint" in source_id:
        return "complaint_memory"
    if domain in {"roads", "stormwater_flooding", "swm", "streetlights"}:
        return "service_issue"
    if domain == "wards":
        return "ward_context"
    return "source_context"


def _source_query_keywords(source: dict[str, Any], answer_focus: str) -> list[str]:
    base = {
        str(source.get("source_id", "")).lower(),
        str(source.get("name", "")).lower(),
        str(source.get("domain", "")).lower(),
        str(source.get("publisher", "")).lower(),
        str(source.get("agency", "")).lower(),
    }
    focus_terms = {
        "money_trail": {
            "award",
            "awarded",
            "bill",
            "contract",
            "contractor",
            "money",
            "paid",
            "payment",
            "procurement",
            "sanction",
            "spend",
            "tender",
            "work",
            "work order",
        },
        "budget_context": {"allocation", "budget", "capital", "estimate", "fund", "outlay", "spend"},
        "complaint_memory": {"complaint", "grievance", "issue", "reported", "status", "recurrence"},
        "service_issue": {"drain", "flooding", "garbage", "pothole", "road", "service", "streetlight", "swm"},
        "ward_context": {"corporation", "ward", "zone", "boundary", "delimitation"},
        "source_context": {"record", "source", "evidence"},
    }
    return sorted(term for term in base | focus_terms.get(answer_focus, focus_terms["source_context"]) if term)


def _source_retrieval_note(source: dict[str, Any], answer_focus: str) -> str:
    if answer_focus == "money_trail":
        return (
            "Use this source for tender, award, contractor, work-order, bill, payment, "
            "and public-spend questions. Do not infer completion or wrongdoing without cited records."
        )
    if answer_focus == "budget_context":
        return "Use this source for budget allocations and spending context; it does not prove local execution by itself."
    if answer_focus == "complaint_memory":
        return "Use this source for reported issue memory, recurrence, status, and evidence pointers."
    if answer_focus == "service_issue":
        return "Use this source for service-specific issue context and then pair it with works or complaint records."
    if answer_focus == "ward_context":
        return "Use this source to resolve ward, corporation, zone, and boundary context before linking civic records."
    return "Use this registered source as supporting context only until normalized usage is available."


def _source_status_rows(
    sources: list[dict[str, Any]],
    profiles: list[dict[str, str]],
    raw_root: Path,
) -> list[dict[str, Any]]:
    profiles_by_id = {row["source_id"]: row for row in profiles}
    rows = []
    for source in sources:
        source_id = str(source.get("id", ""))
        profile = profiles_by_id.get(source_id, {})
        latest = _latest_run(raw_root / source_id)
        manifest = _read_manifest(latest)
        status = str(profile.get("fetched_status") or manifest.get("status") or "not_fetched")
        rows.append(
            {
                "source_id": source_id,
                "name": str(source.get("name", "")),
                "url": str(source.get("url", "")),
                "domain": str(source.get("domain", "")),
                "agency": str(source.get("agency", "")),
                "publisher": str(source.get("publisher", "")),
                "source_tier": int(source.get("source_tier", 0) or 0),
                "official_status": str(source.get("official_status", "")),
                "format": str(source.get("format", "")),
                "access_method": str(source.get("access_method", "")),
                "parser_type": str(source.get("parser_type", "")),
                "license": str(source.get("license", "")),
                "freshness_policy_days": int(source.get("freshness_policy_days", 0) or 0),
                "reliability_score": float(source.get("reliability_score", 0) or 0),
                "pii_risk": str(source.get("pii_risk", "")),
                "enabled": bool(source.get("enabled", True)),
                "notes": str(source.get("notes", "")),
                "latest_fetch_status": status,
                "latest_successful_run": latest.name if latest and status == "success" else None,
                "latest_run": latest.name if latest else None,
                "latest_fetched_at": manifest.get("fetched_at"),
                "file_count": int(profile.get("file_count", 0) or 0),
                "parser_status": _parser_status(profile),
                "freshness_label": _freshness_label(status),
                "caveats": _source_caveats(profile, status),
            }
        )
    return rows


def _payload_source_ids(payload: dict[str, Any]) -> set[str]:
    source_ids = set()
    for citation in _example_citations(payload):
        source_id = citation.get("source_id")
        if source_id:
            source_ids.add(str(source_id))
    for candidate in payload.get("ward_context", {}).get("old_bbmp_candidates", []):
        _add_evidence_source(source_ids, candidate.get("evidence"))
    for candidate in payload.get("ward_context", {}).get("new_gba_candidates", []):
        _add_evidence_source(source_ids, candidate.get("evidence"))
    return source_ids


def _add_evidence_source(source_ids: set[str], evidence: Any) -> None:
    if isinstance(evidence, dict) and evidence.get("source_id"):
        source_ids.add(str(evidence["source_id"]))


def _example_citations(payload: dict[str, Any]) -> list[dict[str, Any]]:
    citations = []
    for issue in payload.get("top_issue_categories", []):
        citations.extend(_issue_citations(issue))
    return _dedupe_citations(citations)[:5]


def _issue_citations(issue: dict[str, Any]) -> list[dict[str, Any]]:
    citations = []
    for example in issue.get("examples", []):
        evidence = example.get("evidence")
        if isinstance(evidence, dict) and evidence.get("source_id"):
            citations.append(
                {
                    "source_id": evidence.get("source_id"),
                    "run_id": evidence.get("run_id"),
                    "raw_file": evidence.get("raw_file"),
                    "row_number": evidence.get("row_number"),
                }
            )
    return _dedupe_citations(citations)[:3]


def _dedupe_citations(citations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    deduped = []
    for citation in citations:
        key = json.dumps(citation, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(citation)
    return deduped


def _payload_known_gaps(place_name: str, payload: dict[str, Any]) -> list[str]:
    gaps = []
    record_scope = payload.get("record_scope", {})
    if not record_scope.get("grievance_date_max"):
        gaps.append(f"{place_name}: no matching grievance records found in the normalized warehouse.")
    freshness_note = str(record_scope.get("freshness_note", ""))
    if "Not a live complaint dashboard" in freshness_note:
        gaps.append(f"{place_name}: grievance view is historical and not a live complaint dashboard.")
    return gaps


def _source_known_gaps(source_rows: list[dict[str, Any]]) -> list[str]:
    gaps = []
    for row in source_rows:
        if row["source_id"] == "bbmp_grievances_data" and row["latest_fetch_status"] == "not_fetched":
            gaps.append("BBMP grievance source has not been fetched in this archive root.")
        if row["latest_fetch_status"] in {"failed", "partial"}:
            gaps.append(f"{row['source_id']}: latest fetch status is {row['latest_fetch_status']}.")
    return gaps


def _with_usage_status(row: dict[str, Any], used_sources: set[str]) -> dict[str, Any]:
    item = dict(row)
    item["normalized_usage_status"] = "used_in_public_claims" if row["source_id"] in used_sources else "registered_only"
    return item


def _source_summary(rows: list[dict[str, Any]], used_sources: set[str]) -> dict[str, int]:
    return {
        "total_sources": len(rows),
        "successful_fetches": sum(1 for row in rows if row["latest_fetch_status"] == "success"),
        "not_fetched": sum(1 for row in rows if row["latest_fetch_status"] == "not_fetched"),
        "used_in_public_claims": len(used_sources),
    }


def _build_warnings(places: list[tuple[str, str]], web_data_root: Path) -> list[str]:
    warnings = []
    payloads = {}
    for _name, slug in places:
        path = web_data_root / "truth" / slug / "all.json"
        if path.exists():
            payloads[slug] = json.loads(path.read_text())
    if "varthur" in payloads and "whitefield" in payloads:
        varthur = payloads["varthur"].get("complaint_summary")
        whitefield = payloads["whitefield"].get("complaint_summary")
        if varthur == whitefield:
            warnings.append(
                "Varthur and Whitefield all-year complaint summaries match; verify whether shared ward/source matching explains this."
            )
    return warnings


def _parser_status(profile: dict[str, str]) -> str:
    if not profile:
        return "not_profiled"
    if profile.get("blocking_issues"):
        return "blocked"
    difficulty = profile.get("parser_difficulty", "")
    if difficulty in {"easy_structured", "medium_structured", "geo_structured"}:
        return "profiled"
    return difficulty or "profiled"


def _freshness_label(status: str) -> str:
    if status == "success":
        return "archive_available"
    if status == "partial":
        return "partial_archive"
    if status == "not_fetched":
        return "not_fetched"
    return "needs_review"


def _source_caveats(profile: dict[str, str], status: str) -> list[str]:
    caveats = []
    if status == "not_fetched":
        caveats.append("No archived fetch run is available for this source root.")
    if profile.get("blocking_issues"):
        caveats.append(str(profile["blocking_issues"]))
    if profile.get("parser_difficulty") in {"html_snapshot_only", "portal_later", "pdf_extract"}:
        caveats.append(f"Parser status requires review: {profile['parser_difficulty']}.")
    return caveats


def _time_range(record_scope: dict[str, Any]) -> str:
    start = record_scope.get("grievance_date_min")
    end = record_scope.get("grievance_date_max")
    if start and end:
        return f"{start} to {end}"
    return "Record date range unavailable"


def _latest_run(source_dir: Path) -> Path | None:
    if not source_dir.exists():
        return None
    runs = [path for path in source_dir.iterdir() if path.is_dir()]
    return sorted(runs)[-1] if runs else None


def _read_manifest(run_dir: Path | None) -> dict[str, Any]:
    if not run_dir:
        return {}
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.exists():
        return {}
    try:
        data = json.loads(manifest_path.read_text())
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _slugify(value: str) -> str:
    import re

    text = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return text or "place"


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True))
