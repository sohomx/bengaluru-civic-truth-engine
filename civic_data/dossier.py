from __future__ import annotations

from pathlib import Path
from typing import Any

from civic_data.truth import build_place_truth


def create_dossier(place: str, warehouse_root: Path, output_path: Path) -> str:
    truth = build_place_truth(place, warehouse_root)
    markdown = render_dossier(truth)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown)
    return markdown


def render_dossier(truth: dict[str, Any]) -> str:
    place = str(truth.get("query", "")).strip()
    if not place:
        raise ValueError("truth payload missing query")
    citations = CitationRegistry()
    context = truth.get("ward_context", {})
    top_categories = _list_of_dicts(truth.get("top_issue_categories"))

    lines: list[str] = [
        f"# Civic Truth Dossier: {place}",
        "",
        "## Executive Summary",
    ]
    lines.extend(_executive_summary_lines(truth))
    lines.extend(
        [
            "",
        "## What Official Records Show",
        ]
    )
    lines.extend(_ward_context_lines(truth, citations))
    lines.extend(
        [
            "",
            "## Complaint Pattern",
            f"- Total complaints found: {_format_count(_total_complaints(truth))}",
        ]
    )
    lines.extend(_counter_lines("By year", truth.get("complaint_summary", {}).get("by_year", [])))
    lines.extend(_counter_lines("By status", truth.get("complaint_summary", {}).get("by_status", [])))
    lines.extend(["", "## Recurring Issue Categories"])
    if not top_categories:
        lines.append("- No complaint categories found for this query.")
    for index, category in enumerate(top_categories[:8], start=1):
        name = str(category.get("category", "")).strip() or "Uncategorized"
        count = int(category.get("count") or 0)
        lines.append(f"{index}. {name}: {_format_count(count)} complaints")
        examples = _list_of_dicts(category.get("examples"))
        for example in examples[:3]:
            lines.append(f"   - {_complaint_example_line(example, citations)}")

    lines.extend(
        [
            "",
            "## Issue Briefs",
        ]
    )
    lines.extend(_issue_brief_lines(top_categories, citations))
    lines.extend(
        [
            "",
            "## Quality Warnings",
            "- This dossier uses archived BBMP grievance records and official ward/delimitation records available in Wave 1.",
            "- Closed status does not prove the issue was actually fixed or stayed fixed.",
            "- Ward matching is text and official-record based; it is not yet geospatially verified.",
            "- Complaint volume can reflect reporting behavior and data coverage, not only ground reality.",
            "",
            "## Claim Discipline",
            "- Can claim: official archived grievance records show the complaint counts and category patterns above.",
            "- Can claim: ward context is based on official ward and delimitation sources where evidence is listed.",
            "- Cannot claim yet: root cause, corruption, contractor responsibility, or current live repair status.",
            "- Community or social signals are excluded from this Wave 1 dossier.",
            "",
            "## Evidence Appendix",
        ]
    )
    _collect_context_evidence(context, citations)
    evidence_lines = citations.lines()
    lines.extend(evidence_lines if evidence_lines else ["- No evidence pointers available."])
    lines.append("")
    return "\n".join(lines)


class CitationRegistry:
    def __init__(self) -> None:
        self._citation_to_id: dict[str, str] = {}

    def cite(self, evidence: Any) -> str:
        citation = _citation(evidence)
        if not citation:
            return ""
        if citation not in self._citation_to_id:
            self._citation_to_id[citation] = f"E{len(self._citation_to_id) + 1}"
        return f"[{self._citation_to_id[citation]}]"

    def lines(self) -> list[str]:
        ordered = sorted(
            self._citation_to_id.items(),
            key=lambda item: int(item[1][1:]),
        )
        return [f"- [{citation_id}]: {citation}" for citation, citation_id in ordered]


def _executive_summary_lines(truth: dict[str, Any]) -> list[str]:
    total = _total_complaints(truth)
    categories = _list_of_dicts(truth.get("top_issue_categories"))
    year_rows = _list_of_dicts(truth.get("complaint_summary", {}).get("by_year", []))
    status_rows = _list_of_dicts(truth.get("complaint_summary", {}).get("by_status", []))
    lines = [f"- Official grievance records show {_format_count(total)} complaints for this query."]
    if categories:
        top = ", ".join(str(item.get("category", "")).strip() for item in categories[:3])
        lines.append(f"- Top recurring categories: {top}.")
    if year_rows:
        peak = max(year_rows, key=lambda item: int(item.get("count") or 0))
        lines.append(
            f"- Peak recorded year: {peak.get('value')} with "
            f"{_format_count(int(peak.get('count') or 0))} complaints."
        )
    closed = next((item for item in status_rows if str(item.get("value", "")).lower() == "closed"), None)
    if closed and total:
        lines.append(
            "- Closure-heavy records should be treated as administrative status, "
            "not proof of durable resolution."
        )
    return lines


def _ward_context_lines(truth: dict[str, Any], citations: CitationRegistry) -> list[str]:
    context = truth.get("ward_context", {})
    old_candidates = _list_of_dicts(context.get("old_bbmp_candidates"))
    new_candidates = _list_of_dicts(context.get("new_gba_candidates"))
    area_candidates = _list_of_dicts(context.get("area_match_candidates"))
    mappings = _list_of_dicts(context.get("old_new_mappings"))
    lines: list[str] = []
    if old_candidates:
        ward = old_candidates[0]
        citation = citations.cite(ward.get("evidence", {}))
        lines.append(
            f"- Old BBMP candidate: {ward.get('ward_name', '')} "
            f"(ward {ward.get('ward_number', '')}) {citation}".rstrip()
        )
    if new_candidates:
        ward = new_candidates[0]
        corporation = str(ward.get("corporation", "")).strip()
        suffix = f", {corporation} Corporation" if corporation else ""
        citation = citations.cite(ward.get("evidence", {}))
        lines.append(
            f"- New GBA candidate: {ward.get('ward_name', '')} "
            f"(ward {ward.get('ward_number', '')}{suffix}) {citation}".rstrip()
        )
    if mappings:
        mapping = mappings[0]
        old_name = str(mapping.get("old_ward_name", "")).strip()
        new_name = str(mapping.get("new_ward_name", "")).strip()
        if old_name and new_name:
            citation = citations.cite(mapping.get("evidence", {}))
            lines.append(
                "- Official old/new mapping: "
                f"{old_name} -> {new_name} "
                f"({mapping.get('method', 'mapping')}) {citation}".rstrip()
            )
    if area_candidates and not old_candidates:
        names = ", ".join(str(item.get("ward_name", "")) for item in area_candidates[:5])
        lines.append(f"- Area-context match includes wards such as: {names}")
    if not lines:
        lines.append("- No ward context matched this query.")
    return lines


def _counter_lines(label: str, rows: Any) -> list[str]:
    values = _list_of_dicts(rows)
    if not values:
        return [f"- {label}: no data"]
    formatted = ", ".join(
        f"{item.get('value')}: {_format_count(int(item.get('count') or 0))}"
        for item in values[:8]
    )
    return [f"- {label}: {formatted}"]


def _issue_brief_lines(
    categories: list[dict[str, Any]], citations: CitationRegistry
) -> list[str]:
    if not categories:
        return ["- No issue briefs available because no issue categories were found."]
    lines: list[str] = []
    for category in categories[:3]:
        name = str(category.get("category", "")).strip() or "Uncategorized"
        count = int(category.get("count") or 0)
        examples = _list_of_dicts(category.get("examples"))
        subcategories = _top_example_values(examples, "issue_subcategory")
        staff = _top_example_values(examples, "staff_name")
        lines.extend(
            [
                f"### {name}",
                f"- Count: {_format_count(count)} complaints",
                f"- Frequent example subcategories: {subcategories or 'not available from examples'}",
                f"- Likely authority clues: {staff or 'not available from examples'}",
            ]
        )
        if examples:
            lines.append(f"- Representative records: {_example_refs(examples, citations)}")
        lines.append("")
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def _top_example_values(examples: list[dict[str, Any]], key: str) -> str:
    values: list[str] = []
    for example in examples:
        value = str(example.get(key, "")).strip()
        if value and value not in values:
            values.append(value)
    return ", ".join(values[:3])


def _example_refs(examples: list[dict[str, Any]], citations: CitationRegistry) -> str:
    refs = []
    for example in examples[:3]:
        complaint_id = str(example.get("external_complaint_id", "")).strip()
        citation = citations.cite(example.get("evidence", {}))
        if complaint_id:
            refs.append(f"Complaint {complaint_id} {citation}".rstrip())
    return "; ".join(refs)


def _complaint_example_line(example: dict[str, Any], citations: CitationRegistry) -> str:
    complaint_id = str(example.get("external_complaint_id", "")).strip()
    subcategory = str(example.get("issue_subcategory", "")).strip()
    date = str(example.get("grievance_date", "")).strip()
    status = str(example.get("status", "")).strip()
    staff = str(example.get("staff_name", "")).strip()
    evidence = citations.cite(example.get("evidence", {}))
    parts = [f"Complaint {complaint_id}"]
    if subcategory:
        parts.append(subcategory)
    if date:
        parts.append(date)
    if status:
        parts.append(status)
    if staff:
        parts.append(f"staff: {staff}")
    if evidence:
        parts.append(evidence)
    return "; ".join(parts)


def _collect_context_evidence(context: Any, citations: CitationRegistry) -> None:
    if not isinstance(context, dict):
        return
    for key in ("old_bbmp_candidates", "new_gba_candidates", "area_match_candidates", "old_new_mappings"):
        for item in _list_of_dicts(context.get(key)):
            citations.cite(item.get("evidence", {}))


def _citation(evidence: Any) -> str:
    if not isinstance(evidence, dict):
        return ""
    source_id = str(evidence.get("source_id", "")).strip()
    if not source_id:
        return ""
    raw_file = str(evidence.get("raw_file", "")).strip()
    row = evidence.get("row_number")
    suffix = ""
    if raw_file:
        suffix += f", {raw_file}"
    if row:
        suffix += f", row {row}"
    return f"{source_id}{suffix}"


def _total_complaints(truth: dict[str, Any]) -> int:
    summary = truth.get("complaint_summary", {})
    if not isinstance(summary, dict):
        return 0
    return int(summary.get("total_complaints") or 0)


def _list_of_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _format_count(value: int) -> str:
    return f"{value:,}"
