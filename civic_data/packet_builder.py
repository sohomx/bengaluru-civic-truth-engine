from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from civic_data.claim_builder import build_citations, build_claims
from civic_data.contracts import contract_metadata, validate_action_packet
from civic_data.evidence_matcher import action_evidence, evidence_rows, match_channels, match_work_records
from civic_data.freshness import build_freshness
from civic_data.issue_router import route_issue
from civic_data.jurisdiction import resolve_jurisdiction
from civic_data.locality import first_place_guess
from civic_data.provenance import evidence_provenance
from civic_data.trace import packet_trace, query_hash
from civic_data.warehouse_reader import NormalizedWarehouse


def build_packet(
    query: str,
    warehouse_root: Path | str = Path("data/normalized"),
    *,
    lat: float | None = None,
    lng: float | None = None,
    xyinfo_client: Callable[[float, float], Any] | None = None,
    locality_alias_path: Path | str | None = Path("data/config/locality_aliases.json"),
) -> dict[str, Any]:
    q = query.strip()
    if not q:
        raise ValueError("--q must not be empty")
    warehouse = NormalizedWarehouse.open(warehouse_root)
    route = route_issue(q)
    capabilities = warehouse.capabilities()
    if not capabilities.packet_inputs_present:
        jurisdiction = resolve_jurisdiction(
            q,
            lat=lat,
            lng=lng,
            warehouse_root=warehouse.root,
            xyinfo_client=xyinfo_client,
            locality_alias_path=locality_alias_path,
        )
        return _insufficient_packet(q, route, jurisdiction, lat=lat, lng=lng, missing=capabilities.missing_packet_inputs)

    jurisdiction = resolve_jurisdiction(
        q,
        lat=lat,
        lng=lng,
        warehouse_root=warehouse.root,
        xyinfo_client=xyinfo_client,
        locality_alias_path=locality_alias_path,
    )
    evidence_matches = match_work_records(q, route, jurisdiction, warehouse.load_works(), warehouse.load_payments())
    channel_matches = match_channels(route, warehouse.load_complaint_channels(), "complaint_channel")
    contact_matches = match_channels(route, warehouse.load_contact_channels(), "contact_channel")
    rows = evidence_rows(evidence_matches)
    citations = build_citations(jurisdiction, evidence_matches, channel_matches, contact_matches)
    claims = build_claims(route, jurisdiction, evidence_matches, channel_matches, contact_matches)
    specificity = _evidence_specificity(q, route, rows)
    limits = _limits(route, jurisdiction, rows, specificity=specificity)
    contacts = _contact_text(channel_matches, contact_matches, route)
    what_to_cite = [row.get("display_claim") or row["text"] for row in rows[:3]] or [
        "Use the jurisdiction and official filing channel; no row-level work/payment evidence matched yet."
    ]
    normalized_place = jurisdiction.get("normalized_ward_name") or first_place_guess(q)
    action = _action(route, jurisdiction, contacts, what_to_cite, limits, has_public_rows=bool(rows))
    evidence_strength = _evidence_strength(jurisdiction, rows)
    evidence_summary = _evidence_summary(rows, specificity=specificity)
    trace = packet_trace(
        query=q,
        jurisdiction=jurisdiction,
        route=route,
        evidence_matches=evidence_matches,
        channel_matches=channel_matches,
        contact_matches=contact_matches,
    )
    provenance = evidence_provenance(
        jurisdiction=jurisdiction,
        evidence_matches=evidence_matches,
        channel_matches=channel_matches,
        contact_matches=contact_matches,
    )
    freshness = build_freshness([match.record for match in evidence_matches + channel_matches + contact_matches])
    packet = {
        "contract": contract_metadata(),
        "schema_version": 3,
        "compatibility_schema_version": 2,
        "packet_type": "civic_action_packet",
        "legacy_packet_type": "civic_evidence_packet",
        "packet_status": "ready",
        "input": {"query": q, "lat": lat, "lng": lng},
        "issue": _issue(route, q),
        "place": _place(normalized_place, jurisdiction),
        "responsibility": _responsibility(route),
        "service_request": _service_request(route),
        "evidence": action_evidence(evidence_matches),
        "evidence_summary": evidence_summary,
        "evidence_strength": evidence_strength,
        "action": action,
        "trace": trace,
        "provenance": provenance,
        "audit": {
            "source_of_truth": "packet_structured_data",
            "legacy_rag_status": "not_used_for_fact_generation",
            "query_hash": query_hash(q),
            "used_rag": False,
            "used_raw_scan": False,
            "resolver_source": jurisdiction.get("source"),
            "total_evidence_matches": len(rows),
            "routing_policy_id": route.get("policy_id"),
            "routing_policy_version": route.get("policy_version"),
            "routing_rule_ids": route.get("routing_rule_ids", []),
            "matcher_versions": {"evidence_matcher": "v3", "issue_router": route.get("policy_version", "routing-v3")},
            "contract_validation_failures": [],
        },
        "question": q,
        "normalized_place": normalized_place or None,
        "normalized_issue": route.get("issue_type"),
        "responsible_agency": route.get("agency"),
        "answer_type": "structured_civic_case",
        "confidence_label": _confidence_label(jurisdiction),
        "short_answer": _short_answer(route, jurisdiction, bool(rows)),
        "jurisdiction": jurisdiction,
        "records_show": _records_show(rows, route),
        "what_to_cite": what_to_cite,
        "who_to_contact": contacts,
        "what_to_do_next": _what_to_do_next(route, jurisdiction),
        "related_works": [row.get("display_claim") or row["text"] for row in rows[:4]] or ["No matching normalized work/payment rows were found."],
        "limits": limits,
        "evidence_table": rows,
        "claims": claims,
        "citations": citations,
        "coverage_gaps": limits,
        "freshness": freshness,
        "retrieval_trace": {
            "backend": "normalized_civic_case",
            "used_raw_scan": False,
            "used_rag": False,
            "works_considered": len(evidence_matches),
            "payments_considered": 0,
            "channels_considered": len(channel_matches) + len(contact_matches),
            "trace_id": trace["trace_id"],
            "routing_rule_ids": route.get("routing_rule_ids", []),
        },
    }
    packet["audit"]["contract_validation_failures"] = validate_action_packet(packet)
    return packet


def render_packet_markdown(packet: dict[str, Any]) -> str:
    issue = packet.get("issue") if isinstance(packet.get("issue"), dict) else {}
    place = packet.get("place") if isinstance(packet.get("place"), dict) else {}
    responsibility = packet.get("responsibility") if isinstance(packet.get("responsibility"), dict) else {}
    action = packet.get("action") if isinstance(packet.get("action"), dict) else {}
    service = packet.get("service_request") if isinstance(packet.get("service_request"), dict) else {}
    evidence = packet.get("evidence") if isinstance(packet.get("evidence"), list) else []
    lines = [
        "# Civic Action Packet",
        "",
        f"Query: {packet.get('question') or packet.get('input', {}).get('query')}",
        f"Issue: {issue.get('display_type') or issue.get('type', 'unknown')}",
        f"Place: {place.get('ward_name') or place.get('normalized_place') or 'unresolved'}",
        f"Likely owner: {_agency_name(responsibility.get('primary_agency'))}",
        f"Evidence strength: {packet.get('evidence_strength', 'none')}",
        "",
        "## Primary action",
        str(action.get("primary_action") or action.get("message_draft") or ""),
        "",
        "## Escalation action",
        str(action.get("escalation_action") or ""),
        "",
        "## Legal or RTI action",
        str(action.get("legal_or_rti_action") or ""),
        "",
        "## What to send",
        str(action.get("message_draft") or ""),
        "",
        "## Required Evidence",
    ]
    for item in service.get("required_fields", []) if isinstance(service.get("required_fields"), list) else []:
        lines.append(f"- {item}")
    lines.extend(["", "## What to Cite"])
    if evidence:
        for item in evidence[:5]:
            if isinstance(item, dict):
                lines.append(f"- {item.get('claim')} [{item.get('source_id')} row {item.get('row_number')}]")
    else:
        for item in packet.get("what_to_cite", []) if isinstance(packet.get("what_to_cite"), list) else []:
            lines.append(f"- {item}")
    lines.extend(["", "## Who to Contact"])
    for item in packet.get("who_to_contact", []) if isinstance(packet.get("who_to_contact"), list) else []:
        lines.append(f"- {item}")
    lines.extend(["", "## What not to claim"])
    not_to_claim = list(service.get("do_not_include", [])) if isinstance(service.get("do_not_include"), list) else []
    not_to_claim.extend(packet.get("limits", []) if isinstance(packet.get("limits"), list) else [])
    for item in not_to_claim:
        lines.append(f"- {item}")
    return "\n".join(lines).rstrip() + "\n"


def _insufficient_packet(
    query: str,
    route: dict[str, Any],
    jurisdiction: dict[str, Any],
    *,
    lat: float | None,
    lng: float | None,
    missing: list[str],
) -> dict[str, Any]:
    limits = [
        "Structured packet inputs are incomplete; RAG/raw fallback was not used for this packet.",
        "Missing normalized packet inputs: " + ", ".join(missing),
    ]
    if jurisdiction.get("caveat"):
        limits.append(str(jurisdiction["caveat"]))
    normalized_place = jurisdiction.get("normalized_ward_name") or first_place_guess(query)
    trace = packet_trace(
        query=query,
        jurisdiction=jurisdiction,
        route=route,
        evidence_matches=[],
        channel_matches=[],
        contact_matches=[],
    )
    provenance = evidence_provenance(
        jurisdiction=jurisdiction,
        evidence_matches=[],
        channel_matches=[],
        contact_matches=[],
    )
    freshness = build_freshness([])
    packet = {
        "contract": contract_metadata(),
        "schema_version": 3,
        "compatibility_schema_version": 2,
        "packet_type": "civic_action_packet",
        "legacy_packet_type": "civic_evidence_packet",
        "packet_status": "insufficient_structured_evidence",
        "input": {"query": query, "lat": lat, "lng": lng},
        "issue": _issue(route, query),
        "place": _place(normalized_place, jurisdiction),
        "responsibility": _responsibility(route),
        "service_request": _service_request(route),
        "evidence": [],
        "evidence_summary": _evidence_summary([], specificity="none"),
        "evidence_strength": _evidence_strength(jurisdiction, []),
        "action": _action(route, jurisdiction, _contact_text([], [], route), [], limits, has_public_rows=False),
        "trace": trace,
        "provenance": provenance,
        "audit": {
            "source_of_truth": "packet_structured_data",
            "legacy_rag_status": "not_used_for_fact_generation",
            "query_hash": query_hash(query),
            "used_rag": False,
            "used_raw_scan": False,
            "resolver_source": jurisdiction.get("source"),
            "missing_packet_inputs": missing,
            "routing_policy_id": route.get("policy_id"),
            "routing_policy_version": route.get("policy_version"),
            "routing_rule_ids": route.get("routing_rule_ids", []),
            "matcher_versions": {"evidence_matcher": "v3", "issue_router": route.get("policy_version", "routing-v3")},
            "contract_validation_failures": [],
        },
        "question": query,
        "normalized_place": normalized_place or None,
        "normalized_issue": route.get("issue_type"),
        "responsible_agency": route.get("agency"),
        "answer_type": "structured_civic_case",
        "confidence_label": _confidence_label(jurisdiction),
        "short_answer": _short_answer(route, jurisdiction, False),
        "jurisdiction": jurisdiction,
        "records_show": [f"No normalized record proves the reported {_issue_display_type(route)} condition yet."],
        "what_to_cite": ["Structured work/payment evidence is unavailable until packet inputs are normalized."],
        "who_to_contact": _contact_text([], [], route),
        "what_to_do_next": _what_to_do_next(route, jurisdiction),
        "related_works": ["No matching normalized work/payment rows were found."],
        "limits": limits,
        "evidence_table": [],
        "claims": [{"claim_type": "coverage_gap", "text": limits[0], "citation_ids": []}],
        "citations": [{"id": "jurisdiction-1", **jurisdiction["evidence"]}] if jurisdiction.get("evidence") else [],
        "coverage_gaps": limits,
        "freshness": freshness,
        "retrieval_trace": {
            "backend": "normalized_civic_case",
            "used_raw_scan": False,
            "used_rag": False,
            "works_considered": 0,
            "payments_considered": 0,
            "channels_considered": 0,
            "trace_id": trace["trace_id"],
            "routing_rule_ids": route.get("routing_rule_ids", []),
        },
    }
    packet["audit"]["contract_validation_failures"] = validate_action_packet(packet)
    return packet


def _issue(route: dict[str, Any], query: str) -> dict[str, Any]:
    return {
        "type": route.get("issue_type"),
        "display_type": _issue_display_type(route),
        "description": query,
        "urgency": "safety" if route.get("issue_type") in {"power", "traffic"} else "unknown",
        "matched_terms": route.get("match_terms", []),
    }


def _place(normalized_place: object, jurisdiction: dict[str, Any]) -> dict[str, Any]:
    return {
        "normalized_place": normalized_place or None,
        "ward_number": jurisdiction.get("ward_number") or "",
        "ward_name": jurisdiction.get("ward_name") or "",
        "corporation": jurisdiction.get("corporation") or "",
        "zone": jurisdiction.get("zone") or "",
        "confidence": jurisdiction.get("confidence") or 0.0,
        "source": jurisdiction.get("source") or "",
        "caveat": jurisdiction.get("caveat") or "",
    }


def _responsibility(route: dict[str, Any]) -> dict[str, Any]:
    return {
        "primary_agency": route.get("agency"),
        "secondary_agencies": route.get("secondary_agencies", []),
        "fallback_agency": {"agency_id": "gba", "name": "Greater Bengaluru Authority / local city corporation"}
        if route.get("issue_type") in {"streetlight", "garbage"}
        else None,
        "ownership_caveat": " ".join(str(item) for item in route.get("proof_limitations", [])),
        "dual_path_caveat": route.get("dual_path_caveat") or "",
        "routing_decision": {
            "policy_id": route.get("policy_id"),
            "policy_version": route.get("policy_version"),
            "rule_ids": route.get("routing_rule_ids", []),
        },
    }


def _service_request(route: dict[str, Any]) -> dict[str, Any]:
    return {
        "open311_like_service_type": route.get("open311_like_service_type"),
        "required_fields": route.get("required_evidence", []),
        "do_not_include": route.get("do_not_include", []),
        "status_policy": route.get("status_policy"),
        "filing_guidance": route.get("filing_guidance"),
    }


def _action(
    route: dict[str, Any],
    jurisdiction: dict[str, Any],
    contacts: list[str],
    what_to_cite: list[str],
    limits: list[str],
    *,
    has_public_rows: bool,
) -> dict[str, Any]:
    evidence = route.get("required_evidence") if isinstance(route.get("required_evidence"), list) else []
    what_not_to_claim = _what_not_to_claim(route, limits)
    message = _message_draft(route, jurisdiction, evidence, what_to_cite, has_public_rows=has_public_rows)
    return {
        "primary_action": _primary_action(route, jurisdiction),
        "escalation_action": _escalation_action(route, contacts),
        "legal_or_rti_action": _legal_or_rti_action(route, jurisdiction),
        "who_to_contact": contacts,
        "what_to_send": _what_to_do_next(route, jurisdiction),
        "evidence_to_attach": evidence,
        "what_not_to_claim": what_not_to_claim,
        "message_draft": message,
    }


def _message_draft(
    route: dict[str, Any],
    jurisdiction: dict[str, Any],
    required_evidence: list[Any],
    what_to_cite: list[str],
    *,
    has_public_rows: bool,
) -> str:
    agency = route.get("agency") if isinstance(route.get("agency"), dict) else {}
    place = jurisdiction.get("ward_name") or "this location"
    issue_label = _issue_display_type(route)
    pieces = [
        f"Hello, I want to report a {issue_label} at {place}.",
    ]
    if jurisdiction.get("ward_number"):
        pieces.append(f"Ward/corporation: {jurisdiction.get('ward_number')} {jurisdiction.get('ward_name')} / {jurisdiction.get('corporation') or 'unknown corporation'}.")
    if required_evidence:
        pieces.append("I can share photos, pin/landmark, date/time, and recurrence details.")
    if has_public_rows:
        pieces.append("For public context: I found public work/payment rows that may help frame the issue; they are not proof of field resolution.")
    else:
        pieces.append("I did not find matching public work/payment rows for this exact issue yet.")
    if route.get("issue_type") in {"water_sewage", "power"}:
        pieces.append("I will share account or private details only inside the official form, not in public messages.")
    if route.get("secondary_agencies"):
        pieces.append(
            "Please route the obstruction or traffic-safety part to Bengaluru Traffic Police, and the digging or repair part to GBA/BBMP; share the official complaint/reference numbers."
        )
    else:
        pieces.append(f"Please route this to {agency.get('name') or 'the responsible team'} and share the official complaint/reference number.")
    return " ".join(pieces)


def _primary_action(route: dict[str, Any], jurisdiction: dict[str, Any]) -> str:
    issue_type = route.get("issue_type")
    place = jurisdiction.get("ward_name") or "the exact location"
    if issue_type == "water_sewage":
        return f"File a BWSSB complaint for {place}; include a photo/video if safe and use account details only inside the official form."
    if issue_type == "power":
        return f"Contact BESCOM for {place}; treat sparking wires, transformer issues, or shock risk as an electrical safety issue."
    if issue_type == "garbage":
        return f"File through BSWML/SWM or the GBA/Sahaaya channel for {place}; include photo, landmark, and recurrence details."
    if issue_type == "streetlight":
        return f"File a civic streetlight maintenance complaint for {place}; include pole number, photo, and landmark or pin."
    if issue_type == "traffic":
        if route.get("secondary_agencies"):
            return (
                f"Use BTP for the immediate obstruction or traffic-safety issue at {place}; "
                "also file a GBA/BBMP civic complaint for the digging, road damage, or repair work."
            )
        return f"Use Bengaluru Traffic Police channels for the traffic disruption at {place}; include time, location, and safe photo/video evidence."
    return f"File through the relevant GBA/BBMP civic channel for {place}; include photo, pin, date/time, and recurrence details."


def _escalation_action(route: dict[str, Any], contacts: list[str]) -> str:
    first_contact = contacts[0] if contacts else str(route.get("filing_guidance") or "the official complaint channel")
    return (
        "If there is no response, follow up with the official complaint/reference number and the same evidence packet. "
        f"Start with: {first_contact}"
    )


def _legal_or_rti_action(route: dict[str, Any], jurisdiction: dict[str, Any]) -> str:
    ward = jurisdiction.get("ward_name")
    context = f" for {ward}" if ward else ""
    return (
        "For a persistent unresolved issue, ask the department for written status, responsible office, and related work/order records"
        f"{context}. Use RTI only for official records; do not include private account details outside official workflows."
    )


def _what_not_to_claim(route: dict[str, Any], limits: list[str]) -> list[str]:
    values = [str(item) for item in route.get("do_not_include", []) if isinstance(item, str)]
    values.extend(str(item) for item in limits if item)
    result: list[str] = []
    for item in values:
        if item not in result:
            result.append(item)
    return result


def _evidence_strength(jurisdiction: dict[str, Any], rows: list[dict[str, str]]) -> str:
    if rows:
        return "public_row"
    if jurisdiction.get("source") == "official_xyinfo":
        return "official_lookup"
    if jurisdiction.get("source") == "locality_alias":
        return "weak"
    return "none"


def _limits(route: dict[str, Any], jurisdiction: dict[str, Any], rows: list[dict[str, str]], *, specificity: str) -> list[str]:
    limits = list(route.get("proof_limitations") or [])
    if rows:
        limits.append("Public work/payment rows are administrative context only; they are not proof of current field condition or field resolution.")
        if specificity == "related":
            limits.append("No exact footpath row matched; listed work/payment rows are related road or drain context only.")
    else:
        limits.append("No normalized work/payment evidence matched this question.")
    if jurisdiction.get("caveat"):
        limits.append(str(jurisdiction["caveat"]))
    return limits


def _contact_text(channel_matches: list[Any], contact_matches: list[Any], route: dict[str, Any]) -> list[str]:
    items = []
    filing_guidance = str(route.get("filing_guidance") or "")
    if filing_guidance:
        items.append(filing_guidance)
    for agency in route.get("secondary_agencies", []) if isinstance(route.get("secondary_agencies"), list) else []:
        if isinstance(agency, dict) and agency.get("agency_id") == "gba":
            items.append("Use GBA/BBMP local corporation channels or Namma Bengaluru/Sahaaya for the civic roadwork part.")
    for match in channel_matches:
        channel = match.record
        name = str(channel.get("name") or "Official complaint channel")
        url = str(channel.get("url") or "")
        items.append(f"{name}: {url}" if url else name)
    for match in contact_matches:
        contact = match.record
        items.append(str(contact.get("name") or contact.get("value") or "Official contact channel"))
    if not items:
        items.append(str(route.get("filing_guidance") or "Use the relevant official complaint channel."))
    return items


def _short_answer(route: dict[str, Any], jurisdiction: dict[str, Any], has_evidence: bool) -> str:
    agency = route.get("agency") if isinstance(route.get("agency"), dict) else {}
    place = jurisdiction.get("ward_name") or "the detected area"
    evidence_text = "I found normalized public evidence rows to cite." if has_evidence else "I did not find matching normalized work/payment rows yet."
    return f"This looks like a {_issue_display_type(route)} around {place}. Likely owner: {agency.get('name')}. {evidence_text}"


def _records_show(rows: list[dict[str, str]], route: dict[str, Any]) -> list[str]:
    if rows:
        return [row.get("display_claim") or row["text"] for row in rows[:3]]
    return [f"No normalized record proves the reported {_issue_display_type(route)} condition yet."]


def _evidence_specificity(query: str, route: dict[str, Any], rows: list[dict[str, str]]) -> str:
    if not rows:
        return "none"
    text = query.lower()
    labels = {str(row.get("relevance_label") or "").lower() for row in rows}
    if "footpath" in text and not any("footpath" in label for label in labels):
        return "related"
    if any(label.startswith("direct") or "streetlight" in label for label in labels):
        return "direct"
    if route.get("issue_type") in {"garbage", "water_sewage", "power", "traffic"}:
        return "none"
    return "related"


def _evidence_summary(rows: list[dict[str, str]], *, specificity: str) -> dict[str, Any]:
    shown = min(3, len(rows))
    return {
        "shown_count": shown,
        "total_matches": len(rows),
        "hidden_count": max(0, len(rows) - shown),
        "specificity": specificity,
    }


def _issue_display_type(route: dict[str, Any]) -> str:
    issue_type = str(route.get("issue_type") or "civic")
    return {
        "water_sewage": "sewage/water issue",
        "power": "power issue",
        "traffic": "traffic or road-blocking issue",
        "garbage": "garbage or dumping issue",
        "streetlight": "streetlight issue",
        "road": "road or footpath issue",
        "civic": "civic issue",
    }.get(issue_type, "civic issue")


def _what_to_do_next(route: dict[str, Any], jurisdiction: dict[str, Any]) -> list[str]:
    evidence = route.get("required_evidence") if isinstance(route.get("required_evidence"), list) else []
    items = [f"File through: {route.get('filing_guidance')}"]
    if jurisdiction.get("ward_name"):
        items.append(f"Mention ward/corporation context: {jurisdiction.get('ward_name')} / {jurisdiction.get('corporation') or 'unknown corporation'}.")
    if evidence:
        items.append("Attach or mention: " + ", ".join(str(item) for item in evidence[:4]) + ".")
    return items


def _freshness(records: list[dict[str, Any]]) -> dict[str, Any]:
    fetched = sorted({str(item.get("fetched_at")) for item in records if item.get("fetched_at")})
    return {"fetched_at_values": fetched[:5], "basis": "normalized_public_records"}


def _confidence_label(jurisdiction: dict[str, Any]) -> str:
    confidence = float(jurisdiction.get("confidence") or 0.0)
    if confidence >= 0.9:
        return "high"
    if confidence >= 0.5:
        return "medium"
    return "low"


def _agency_name(value: object) -> str:
    return str(value.get("name") or "unknown") if isinstance(value, dict) else "unknown"


def dumps_packet(packet: dict[str, Any]) -> str:
    return json.dumps(packet, indent=2, sort_keys=True)
