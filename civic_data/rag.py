from __future__ import annotations

import csv
import json
import re
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from civic_data.normalize import normalize_name


MAX_CHUNKS = 12
ISSUE_BUCKET_LIMIT = 5000
WORK_SOURCE_TOKENS = ("work_orders", "work_order", "payments", "payment", "bill")
TENDER_SOURCE_TOKENS = ("tender", "kppp", "procurement")
STREETLIGHT_SOURCE_TOKENS = ("streetlight", "streetlights", "bescom")
DEFAULT_RAG_INDEX_NAME = "rag_index.json"
ISSUE_ALIASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("streetlight", ("street light", "street lights", "streetlight", "streetlights", "streetlite", "street lites", "st light", "st lights", "st lite", "st lites", "bescom", "light pole", "lamp post", "not working", "wrking", "failing", "fail again")),
    ("garbage", ("garbage", "garbge", "solid waste", "swm", "waste", "trash", "rubbish", "dump")),
    ("drain", ("drain", "drains", "swd", "storm water", "stormwater", "rajakaluve", "flood", "floods", "flooding", "water logging", "waterlogging")),
    ("road", ("road", "roads", "pothole", "pothol", "potholes", "asphalt", "footpath", "sidewalk")),
)


def ask_rag(
    query: str,
    warehouse_root: Path | str = Path("data/normalized"),
    raw_root: Path | str = Path("data/raw"),
    index_path: Path | str | None = None,
    rag_index: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    q = query.strip()
    if not q:
        raise ValueError("--q must not be empty")
    warehouse = Path(warehouse_root)
    raw = Path(raw_root)
    loaded_index_path = _default_index_path(warehouse, index_path)
    indexed_chunks = rag_index if rag_index is not None else load_rag_index(loaded_index_path)
    intent = interpret_intent(q)
    planned_at = time.perf_counter()
    wards = _read_json_list(warehouse / "wards.json")
    mappings = _read_json_list(warehouse / "old_new_ward_mappings.json")
    detected = detect_places(q, wards, mappings)
    relevant_names = _relevant_place_names(detected, mappings)
    place_numbers = _relevant_ward_numbers(detected, mappings)
    resolved_at = time.perf_counter()

    chunks: list[dict[str, Any]] = []
    if intent["needs_complaints"]:
        if indexed_chunks is not None:
            candidates = _indexed_candidates(indexed_chunks, ("complaint",), relevant_names, intent)
            chunks.extend(_indexed_chunks(candidates, ("complaint",), q, relevant_names, place_numbers, None))
        else:
            chunks.extend(_complaint_chunks(warehouse / "complaints.json", q, relevant_names))
    if intent["needs_money"] or (intent["needs_related_money"] and detected):
        money_terms = _money_context_terms(q) if intent["needs_service"] else []
        if indexed_chunks is not None:
            work_candidates = _indexed_candidates(indexed_chunks, ("work_payment",), relevant_names, intent)
            tender_candidates = _indexed_candidates(indexed_chunks, ("tender",), relevant_names, intent)
            chunks.extend(_indexed_chunks(work_candidates, ("work_payment",), q, relevant_names, place_numbers, money_terms))
            chunks.extend(_indexed_chunks(tender_candidates, ("tender",), q, relevant_names, place_numbers, money_terms))
        else:
            chunks.extend(_raw_csv_chunks(raw, q, relevant_names, place_numbers, WORK_SOURCE_TOKENS, "work_payment", money_terms))
            chunks.extend(_raw_csv_chunks(raw, q, relevant_names, place_numbers, TENDER_SOURCE_TOKENS, "tender", money_terms))
    if intent["needs_streetlight_assets"]:
        if indexed_chunks is not None:
            candidates = _indexed_candidates(indexed_chunks, ("streetlight_asset",), relevant_names, intent)
            chunks.extend(_indexed_chunks(candidates, ("streetlight_asset",), q, relevant_names, place_numbers, None))
        else:
            chunks.extend(_raw_csv_chunks(raw, q, relevant_names, place_numbers, STREETLIGHT_SOURCE_TOKENS, "streetlight_asset"))
    retrieved_at = time.perf_counter()

    ranked_all = _rank_chunks(chunks, q, relevant_names, place_numbers)
    ranked = _select_retrieved_chunks(ranked_all, MAX_CHUNKS)
    gaps = _coverage_gaps(q, intent, ranked_all, detected)
    extractive = _extractive_answer(q, intent, detected, ranked_all)
    structured_stats = _structured_complaint_stats(
        indexed_chunks=indexed_chunks,
        warehouse_root=warehouse,
        query=q,
        intent=intent,
        relevant_names=relevant_names,
    )
    if structured_stats:
        extractive = _apply_structured_complaint_stats(extractive, structured_stats, detected)
    citations = _dedupe_citations([chunk["citation"] for chunk in ranked if chunk.get("citation")])
    freshness = _freshness(ranked_all)
    if structured_stats.get("latest_record_date"):
        freshness["latest_record_date"] = structured_stats["latest_record_date"]
    triage = _civic_triage(q, intent, detected, extractive, ranked, gaps, freshness)
    generated = _generated_answer(triage, ranked, gaps, freshness)
    answer_brief = _answer_brief(triage, extractive, gaps, freshness)
    composed_at = time.perf_counter()
    payload = {
        "query": q,
        "interpreted_intent": intent["label"],
        "detected_places": [place["normalized_name"] for place in detected],
        "retrieved_chunks": ranked,
        "extractive_answer": extractive,
        "civic_triage": triage,
        "answer_brief": answer_brief,
        "generated_answer": generated,
        "citations": citations,
        "coverage_gaps": gaps,
        "freshness": freshness,
    }
    payload.update(
        _answer_contract_fields(
            query=q,
            intent=intent,
            detected_places=detected,
            extractive=extractive,
            triage=triage,
            citations=citations,
            gaps=gaps,
            freshness=freshness,
            indexed_chunks=indexed_chunks,
            loaded_index_path=loaded_index_path,
            timings={
                "planner": planned_at - started,
                "place_resolution": resolved_at - planned_at,
                "retrieval": retrieved_at - resolved_at,
                "answer_contract": composed_at - retrieved_at,
                "total": composed_at - started,
            },
        )
    )
    _validate_answer_contract(payload)
    return payload


def build_rag_index(
    warehouse_root: Path | str = Path("data/normalized"),
    raw_root: Path | str = Path("data/raw"),
    output_path: Path | str | None = None,
) -> dict[str, Any]:
    warehouse = Path(warehouse_root)
    raw = Path(raw_root)
    output = Path(output_path) if output_path else warehouse / DEFAULT_RAG_INDEX_NAME
    bucket_dir = output.with_suffix("")
    chunks: list[dict[str, Any]] = []
    chunks.extend(_all_complaint_chunks(warehouse / "complaints.json"))
    normalized_work_payment_chunks = _all_normalized_work_payment_chunks(warehouse)
    if normalized_work_payment_chunks:
        chunks.extend(normalized_work_payment_chunks)
    else:
        chunks.extend(_all_raw_csv_chunks(raw, WORK_SOURCE_TOKENS, "work_payment"))
    chunks.extend(_all_raw_csv_chunks(raw, TENDER_SOURCE_TOKENS, "tender"))
    chunks.extend(_all_raw_csv_chunks(raw, STREETLIGHT_SOURCE_TOKENS, "streetlight_asset"))
    indexed = [_index_chunk(chunk) for chunk in chunks]
    wards = _read_json_list(warehouse / "wards.json")
    mappings = _read_json_list(warehouse / "old_new_ward_mappings.json")
    buckets = _bucket_index_chunks(indexed, wards, mappings)
    bucket_dir.mkdir(parents=True, exist_ok=True)
    bucket_manifest: dict[str, str] = {}
    for key, bucket_chunks in sorted(buckets.items()):
        persisted_chunks = _trim_bucket_for_storage(key, bucket_chunks)
        bucket_path = bucket_dir / f"{_bucket_filename(key)}.json"
        bucket_path.write_text(json.dumps(persisted_chunks, ensure_ascii=True, separators=(",", ":")))
        bucket_manifest[key] = str(bucket_path.relative_to(output.parent))
    payload = {
        "schema_version": 2,
        "storage": "bucketed-json",
        "built_at": datetime.now(timezone.utc).isoformat(),
        "warehouse_root": str(warehouse),
        "raw_root": str(raw),
        "chunk_count": len(indexed),
        "bucket_dir": str(bucket_dir.relative_to(output.parent)),
        "buckets": bucket_manifest,
        "structured_aggregates": _structured_aggregates_for_buckets(buckets),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=True, separators=(",", ":")))
    return {
        "index_path": str(output),
        "chunk_count": len(indexed),
        "schema_version": 2,
        "built_at": payload["built_at"],
    }


def load_rag_index(index_path: Path | str | None) -> Any:
    if index_path is None:
        return None
    path = Path(index_path)
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    if isinstance(data, dict) and data.get("storage") == "bucketed-json":
        data["_index_path"] = str(path)
        return data
    if not isinstance(data, dict) or not isinstance(data.get("chunks"), list):
        raise ValueError(f"{path} must contain a RAG index with chunks")
    return [chunk for chunk in data["chunks"] if isinstance(chunk, dict)]


def interpret_intent(query: str) -> dict[str, Any]:
    text = query.lower()
    issue_keys = _query_issue_keys(text)
    needs_streetlight_assets = "streetlight" in issue_keys
    needs_money = bool(
        re.search(r"\b(tender|tenders|award|awarded|contractor|contract|work orders?|payment|paid|bill|budget|spend|money|sanction)\b", text)
    )
    needs_service = bool(issue_keys)
    needs_complaints = bool(
        re.search(r"\b(complaint|complaints|grievance|reported|status|recurring|recurrence|history|happened before|past|not working)\b", text)
    )
    if needs_service:
        needs_complaints = True
    labels = []
    if needs_money:
        labels.append("money_trail")
    if needs_service:
        labels.append("service_issue")
    if needs_complaints:
        labels.append("complaint_memory")
    return {
        "label": "+".join(labels) if labels else "source_context",
        "needs_money": needs_money,
        "needs_service": needs_service,
        "needs_complaints": needs_complaints,
        "needs_streetlight_assets": needs_streetlight_assets,
        "needs_related_money": needs_service,
        "issue_keys": issue_keys,
    }


def detect_places(query: str, wards: list[dict[str, Any]], mappings: list[dict[str, Any]]) -> list[dict[str, str]]:
    normalized_query = normalize_name(query)
    candidates: dict[str, dict[str, str]] = {}
    for ward in wards:
        normalized = str(ward.get("normalized_name", "")).strip()
        if not normalized:
            continue
        aliases = {normalized, _without_terminal_u(normalized)}
        ward_name = str(ward.get("ward_name", "")).strip()
        ward_number = str(ward.get("ward_number", "")).strip()
        for alias in aliases:
            if alias and _contains_phrase(normalized_query, alias):
                candidates[normalized] = {
                    "normalized_name": _canonical_place_name(alias if alias in normalized_query else normalized),
                    "ward_name": ward_name,
                    "ward_number": ward_number,
                }
    for mapping in mappings:
        for key in ("old_ward_name", "new_ward_name"):
            normalized = normalize_name(str(mapping.get(key, "")))
            alias = _without_terminal_u(normalized)
            if alias and _contains_phrase(normalized_query, alias):
                candidates[normalized] = {
                    "normalized_name": _canonical_place_name(alias),
                    "ward_name": str(mapping.get(key, "")),
                    "ward_number": str(mapping.get(key.replace("name", "number"), "")),
                }
    return list(candidates.values())


def _complaint_chunks(path: Path, query: str, relevant_names: set[str]) -> list[dict[str, Any]]:
    issue_terms = _issue_terms(query)
    chunks = []
    for complaint in _read_json_list(path):
        place = normalize_name(str(complaint.get("normalized_ward_name", "")))
        if relevant_names and place not in relevant_names and _without_terminal_u(place) not in relevant_names:
            continue
        text = " ".join(
            str(complaint.get(key, ""))
            for key in ("issue_category", "issue_subcategory", "status", "staff_remarks", "ward_name_raw")
        )
        if issue_terms and not _matches_any(text, issue_terms):
            continue
        chunks.append(_complaint_to_chunk(complaint))
    return chunks


def _all_complaint_chunks(path: Path) -> list[dict[str, Any]]:
    return [_complaint_to_chunk(complaint) for complaint in _read_json_list(path)]


def _complaint_to_chunk(complaint: dict[str, Any]) -> dict[str, Any]:
    evidence = complaint.get("evidence") if isinstance(complaint.get("evidence"), dict) else {}
    return {
        "chunk_type": "complaint",
        "source_id": evidence.get("source_id", "bbmp_grievances_data"),
        "title": f"{complaint.get('issue_subcategory') or complaint.get('issue_category')} complaint",
        "text": (
            f"{complaint.get('ward_name_raw', '')}: {complaint.get('issue_category', '')} / "
            f"{complaint.get('issue_subcategory', '')}; status {complaint.get('status', '')}; "
            f"date {complaint.get('grievance_date', '')}; complaint {complaint.get('external_complaint_id', '')}."
        ),
        "fields": {
            "external_complaint_id": complaint.get("external_complaint_id"),
            "issue_category": complaint.get("issue_category"),
            "issue_subcategory": complaint.get("issue_subcategory"),
            "status": complaint.get("status"),
            "grievance_date": complaint.get("grievance_date"),
            "ward_name": complaint.get("ward_name_raw"),
            "staff_name": complaint.get("staff_name"),
            "staff_remarks": complaint.get("staff_remarks"),
        },
        "citation": _citation(evidence),
    }


def _all_raw_csv_chunks(
    raw_root: Path,
    source_tokens: tuple[str, ...],
    chunk_type: str,
) -> list[dict[str, Any]]:
    chunks = []
    for run_dir in _matching_run_dirs(raw_root, source_tokens):
        for file_path in _manifest_csv_files(run_dir):
            for row_number, row in _read_csv_rows(file_path):
                chunks.append(_csv_chunk(chunk_type, run_dir, file_path, row_number, row))
    return chunks


def _all_normalized_work_payment_chunks(warehouse_root: Path) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    for record in _read_json_list(warehouse_root / "works.json"):
        chunks.append(_normalized_work_payment_chunk(record, "work"))
    for record in _read_json_list(warehouse_root / "payments.json"):
        chunks.append(_normalized_work_payment_chunk(record, "payment"))
    return chunks


def _normalized_work_payment_chunk(record: dict[str, Any], entity_type: str) -> dict[str, Any]:
    evidence = record.get("evidence") if isinstance(record.get("evidence"), dict) else {}
    description = str(record.get("description") or record.get("payment_reference") or "")
    amount = record.get("amount") or record.get("net_amount") or ""
    text = (
        f"{description}; contractor {record.get('contractor', '')}; amount {amount}; "
        f"ward {record.get('ward_number', '')}; ward regime {record.get('ward_regime', '')}."
    )
    return {
        "chunk_type": "work_payment",
        "entity_type": entity_type,
        "source_id": record.get("source_id") or evidence.get("source_id"),
        "title": _clean_text(description or f"{entity_type.title()} row"),
        "text": _clean_text(text),
        "fields": {
            "work_id": record.get("work_id"),
            "payment_id": record.get("payment_id"),
            "ward": record.get("ward_number"),
            "ward_regime": record.get("ward_regime"),
            "description": record.get("description"),
            "payment_reference": record.get("payment_reference"),
            "contractor": record.get("contractor"),
            "amount": record.get("amount"),
            "net_amount": record.get("net_amount"),
            "claim_class": record.get("claim_class"),
            "allowed_claims": record.get("allowed_claims"),
            "disallowed_claims": record.get("disallowed_claims"),
            "freshness_basis": record.get("freshness_basis"),
            "parser_version": record.get("parser_version"),
        },
        "claim_class": record.get("claim_class"),
        "allowed_claims": record.get("allowed_claims"),
        "disallowed_claims": record.get("disallowed_claims"),
        "freshness_basis": record.get("freshness_basis"),
        "parser_version": record.get("parser_version"),
        "citation": _citation(evidence),
    }


def _bucket_index_chunks(
    chunks: list[dict[str, Any]],
    wards: list[dict[str, Any]],
    mappings: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    known_names, number_to_names = _known_place_index(wards, mappings)
    buckets: dict[str, list[dict[str, Any]]] = {}
    for chunk in chunks:
        chunk_type = str(chunk.get("chunk_type", ""))
        for place_key in _chunk_place_keys(chunk, known_names, number_to_names):
            _append_bucket(buckets, f"{chunk_type}:place:{place_key}", chunk)
        for issue_key in _chunk_issue_keys(chunk):
            _append_bucket(buckets, f"{chunk_type}:issue:{issue_key}", chunk)
    return buckets


def _indexed_candidates(
    rag_index: Any,
    chunk_types: tuple[str, ...],
    relevant_names: set[str],
    intent: dict[str, Any],
) -> list[dict[str, Any]]:
    if isinstance(rag_index, list):
        return rag_index
    if not isinstance(rag_index, dict) or rag_index.get("storage") != "bucketed-json":
        return []
    buckets = rag_index.get("buckets") if isinstance(rag_index.get("buckets"), dict) else {}
    index_path = Path(str(rag_index.get("_index_path", "")))
    base = index_path.parent if index_path else Path(".")
    keys: list[str] = []
    for chunk_type in chunk_types:
        for name in sorted(relevant_names):
            keys.append(f"{chunk_type}:place:{name}")
        if not relevant_names:
            for issue in _intent_issue_keys(intent):
                keys.append(f"{chunk_type}:issue:{issue}")
    seen = set()
    candidates: list[dict[str, Any]] = []
    for key in keys:
        relative = buckets.get(key)
        if not isinstance(relative, str):
            continue
        path = base / relative
        if not path.exists():
            continue
        for chunk in json.loads(path.read_text()):
            if not isinstance(chunk, dict):
                continue
            identity = _chunk_identity(chunk)
            if identity in seen:
                continue
            candidates.append(chunk)
            seen.add(identity)
    return candidates


def _append_bucket(
    buckets: dict[str, list[dict[str, Any]]],
    key: str,
    chunk: dict[str, Any],
    limit: int | None = None,
) -> None:
    bucket = buckets.setdefault(key, [])
    if limit is not None and len(bucket) >= limit:
        return
    bucket.append(chunk)


def _trim_bucket_for_storage(key: str, chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if ":issue:" not in key or len(chunks) <= ISSUE_BUCKET_LIMIT:
        return chunks
    return sorted(chunks, key=_descending_date_key)[:ISSUE_BUCKET_LIMIT]


def _known_place_index(
    wards: list[dict[str, Any]],
    mappings: list[dict[str, Any]],
) -> tuple[set[str], dict[str, set[str]]]:
    names: set[str] = set()
    number_to_names: dict[str, set[str]] = {}
    for ward in wards:
        normalized = normalize_name(str(ward.get("normalized_name") or ward.get("ward_name") or ""))
        if not normalized:
            continue
        aliases = {normalized, _without_terminal_u(normalized)}
        names.update(alias for alias in aliases if alias)
        number = str(ward.get("ward_number", "")).strip()
        if number:
            number_to_names.setdefault(number, set()).update(alias for alias in aliases if alias)
    for mapping in mappings:
        old_name = normalize_name(str(mapping.get("old_ward_name", "")))
        new_name = normalize_name(str(mapping.get("new_ward_name", "")))
        aliases = {old_name, new_name, _without_terminal_u(old_name), _without_terminal_u(new_name)}
        aliases = {alias for alias in aliases if alias}
        names.update(aliases)
        for key in ("old_ward_number", "new_ward_number"):
            number = str(mapping.get(key, "")).strip()
            if number:
                number_to_names.setdefault(number, set()).update(aliases)
    return names, number_to_names


def _chunk_place_keys(
    chunk: dict[str, Any],
    known_names: set[str],
    number_to_names: dict[str, set[str]],
) -> set[str]:
    fields = chunk.get("fields") if isinstance(chunk.get("fields"), dict) else {}
    search_text = str(chunk.get("search_text", ""))
    keys = set(_place_name_ngrams(search_text, known_names))
    ward_name = normalize_name(str(fields.get("ward_name", "")))
    if ward_name in known_names:
        keys.add(ward_name)
    ward_alias = _without_terminal_u(ward_name)
    if ward_alias in known_names:
        keys.add(ward_alias)
    for key, value in fields.items():
        normalized_key = str(key).lower()
        value_text = str(value).strip()
        if normalized_key in {"ward", "ward_no", "ward no", "ward number", "ward_no_name"} and value_text in number_to_names:
            keys.update(number_to_names[value_text])
        if "ward" in normalized_key:
            for number in re.findall(r"\b\d{1,3}\b", value_text):
                if number in number_to_names:
                    keys.update(number_to_names[number])
    for number in re.findall(r"\bward\s*(?:no\.?|number)?\s*-?\s*(\d{1,3})\b", search_text, re.IGNORECASE):
        if number in number_to_names:
            keys.update(number_to_names[number])
    return {key for key in keys if key}


def _place_name_ngrams(text: str, known_names: set[str]) -> set[str]:
    if not text:
        return set()
    words = text.split()
    matches = set()
    max_width = 4
    for index in range(len(words)):
        for width in range(1, max_width + 1):
            phrase = " ".join(words[index : index + width])
            if phrase in known_names:
                matches.add(phrase)
    return matches


def _chunk_issue_keys(chunk: dict[str, Any]) -> set[str]:
    text = str(chunk.get("search_text", ""))
    return set(_query_issue_keys(text))


def _intent_issue_keys(intent: dict[str, Any]) -> list[str]:
    keys = intent.get("issue_keys")
    if isinstance(keys, list):
        return [str(key) for key in keys if key]
    return ["streetlight"] if intent.get("needs_streetlight_assets") else []


def _query_issue_keys(text: str) -> list[str]:
    normalized = normalize_name(text)
    keys = []
    for key, aliases in ISSUE_ALIASES:
        if _matches_any(normalized, list(aliases)):
            keys.append(key)
    return keys


def _bucket_filename(key: str) -> str:
    return re.sub(r"[^a-z0-9._-]+", "_", key.lower()).strip("_")


def _raw_csv_chunks(
    raw_root: Path,
    query: str,
    relevant_names: set[str],
    place_numbers: set[str],
    source_tokens: tuple[str, ...],
    chunk_type: str,
    required_terms: list[str] | None = None,
) -> list[dict[str, Any]]:
    chunks = []
    for run_dir in _matching_run_dirs(raw_root, source_tokens):
        for file_path in _manifest_csv_files(run_dir):
            for row_number, row in _read_csv_rows(file_path):
                row_text = " ".join(str(value) for value in row.values())
                if relevant_names or place_numbers:
                    if not _row_matches_place(row, row_text, relevant_names, place_numbers):
                        continue
                elif not _row_matches_terms(row_text, query):
                    continue
                if required_terms and not _matches_any(row_text, required_terms):
                    continue
                if not _row_matches_terms(row_text, query) and relevant_names:
                    if chunk_type in {"work_payment", "tender"} and not _matches_any(row_text, ["work", "road", "drain", "street", "light", "payment", "tender"]):
                        continue
                chunks.append(_csv_chunk(chunk_type, run_dir, file_path, row_number, row))
    return chunks


def _indexed_chunks(
    indexed_chunks: list[dict[str, Any]],
    chunk_types: tuple[str, ...],
    query: str,
    relevant_names: set[str],
    place_numbers: set[str],
    required_terms: list[str] | None,
) -> list[dict[str, Any]]:
    issue_terms = _issue_terms(query)
    chunks = []
    for chunk in indexed_chunks:
        if chunk.get("chunk_type") not in chunk_types:
            continue
        search_text = str(chunk.get("search_text") or normalize_name(f"{chunk.get('title', '')} {chunk.get('text', '')}"))
        fields = chunk.get("fields") if isinstance(chunk.get("fields"), dict) else {}
        if relevant_names or place_numbers:
            if not _row_matches_place(fields, search_text, relevant_names, place_numbers):
                continue
        elif chunk.get("chunk_type") != "complaint" and not _row_matches_terms(search_text, query):
            continue
        if chunk.get("chunk_type") == "complaint" and issue_terms and not _matches_any(search_text, issue_terms):
            continue
        if required_terms and not _matches_any(search_text, required_terms):
            continue
        if (
            chunk.get("chunk_type") in {"work_payment", "tender"}
            and relevant_names
            and not _row_matches_terms(search_text, query)
            and not _matches_any(search_text, ["work", "road", "drain", "street", "light", "payment", "tender"])
        ):
            continue
        chunks.append({key: value for key, value in chunk.items() if key != "search_text"})
    return chunks


def _csv_chunk(chunk_type: str, run_dir: Path, file_path: Path, row_number: int, row: dict[str, str]) -> dict[str, Any]:
    source_id = run_dir.parent.name
    if chunk_type == "work_payment":
        title = _first_value(row, "wodetails", "Name of Work", "Work Name", "Job Number") or "Work/payment row"
        text = (
            f"{title}; contractor {_first_value(row, 'contractor', 'Contractor', 'Name of contractor')}; "
            f"amount {_first_value(row, 'amount', 'Gross', 'Tender Value in Rs')}; "
            f"net {_first_value(row, 'nett', 'Nett')}; ward {_first_value(row, 'ward', 'Ward')}; "
            f"bill/payment {_first_value(row, 'brnumber', 'BR Number', 'Payment', 'BR', 'RTGS')}."
        )
    elif chunk_type == "tender":
        title = _first_value(row, "Tender Title", "title") or "Tender row"
        text = (
            f"{title}; tender number {_first_value(row, 'Tender Number')}; "
            f"value {_first_value(row, 'Tender Value in Rs')}; department {_first_value(row, 'Department-Location')}; "
            f"published {_first_value(row, 'Published Date')}."
        )
    elif chunk_type == "streetlight_asset":
        title = _first_value(row, "Ward Name", "Zone & Location", "Streetlight Code") or "Streetlight row"
        text = (
            f"{title}; ward {_first_value(row, 'Ward_No', 'Ward')}; "
            f"streetlights {_first_value(row, 'Street lights #', 'Street lights\\r#')}; "
            f"condition {_first_value(row, 'Condition on 2-July-19', 'Condition on 17-June-19')}; "
            f"remarks {_first_value(row, 'Remarks')}."
        )
    else:
        title = "Source row"
        text = " ".join(row.values())
    return {
        "chunk_type": chunk_type,
        "source_id": source_id,
        "title": _clean_text(title),
        "text": _clean_text(text),
        "fields": {str(k): str(v) for k, v in row.items() if str(v).strip()},
        "citation": {
            "source_id": source_id,
            "run_id": run_dir.name,
            "raw_file": str(file_path.relative_to(run_dir)),
            "row_number": row_number,
        },
    }


def _extractive_answer(query: str, intent: dict[str, Any], detected_places: list[dict[str, str]], chunks: list[dict[str, Any]]) -> dict[str, Any]:
    complaints = [chunk for chunk in chunks if chunk["chunk_type"] == "complaint"]
    works = [chunk for chunk in chunks if chunk["chunk_type"] == "work_payment"]
    tenders = [chunk for chunk in chunks if chunk["chunk_type"] == "tender"]
    streetlights = [chunk for chunk in chunks if chunk["chunk_type"] == "streetlight_asset"]
    dates = sorted(str(chunk.get("fields", {}).get("grievance_date", "")) for chunk in complaints if chunk.get("fields", {}).get("grievance_date"))
    status_counts = Counter(str(chunk.get("fields", {}).get("status", "")) for chunk in complaints if chunk.get("fields", {}).get("status"))
    return {
        "summary": _summary_sentence(query, complaints, works, tenders, streetlights, detected_places),
        "complaint_count": len(complaints),
        "latest_record_date": dates[-1] if dates else None,
        "status_breakdown": dict(status_counts),
        "work_payment_count": len(works),
        "tender_count": len(tenders),
        "streetlight_asset_count": len(streetlights),
        "example_ids": [chunk["fields"].get("external_complaint_id") for chunk in complaints[:5] if chunk["fields"].get("external_complaint_id")],
    }


def _structured_complaint_stats(
    indexed_chunks: Any,
    warehouse_root: Path,
    query: str,
    intent: dict[str, Any],
    relevant_names: set[str],
) -> dict[str, Any]:
    stats = _structured_complaint_stats_from_index(indexed_chunks, intent, relevant_names)
    if stats:
        return stats
    if indexed_chunks is not None:
        return {}
    return _structured_complaint_stats_from_warehouse(warehouse_root, query, relevant_names)


def _structured_complaint_stats_from_index(
    indexed_chunks: Any,
    intent: dict[str, Any],
    relevant_names: set[str],
) -> dict[str, Any]:
    if not isinstance(indexed_chunks, dict):
        return {}
    aggregates = indexed_chunks.get("structured_aggregates")
    if not isinstance(aggregates, dict):
        return {}
    keys = []
    if relevant_names:
        issue_keys = _intent_issue_keys(intent)
        if issue_keys:
            for name in sorted(relevant_names):
                keys.extend(f"complaint:place:{name}:issue:{issue}" for issue in issue_keys)
        else:
            keys.extend(f"complaint:place:{name}" for name in sorted(relevant_names))
        selected = [aggregates[key] for key in keys if isinstance(aggregates.get(key), dict)]
        if not selected:
            return {}
        return max(selected, key=lambda item: int(item.get("complaint_count") or 0))
    else:
        keys.extend(f"complaint:issue:{issue}" for issue in _intent_issue_keys(intent))
        selected = [aggregates[key] for key in keys if isinstance(aggregates.get(key), dict)]
        return _merge_complaint_stats(selected)


def _structured_complaint_stats_from_warehouse(
    warehouse_root: Path,
    query: str,
    relevant_names: set[str],
) -> dict[str, Any]:
    path = warehouse_root / "complaints.json"
    if not path.exists():
        return {}
    chunks = _complaint_chunks(path, query, relevant_names)
    return _complaint_stats(chunks)


def _structured_aggregates_for_buckets(buckets: dict[str, list[dict[str, Any]]]) -> dict[str, dict[str, Any]]:
    aggregates = {}
    for key, chunks in buckets.items():
        if key.startswith("complaint:"):
            aggregates[key] = _complaint_stats(chunks)
            if ":place:" in key and ":issue:" not in key:
                issue_buckets: dict[str, list[dict[str, Any]]] = {}
                for chunk in chunks:
                    for issue_key in _chunk_issue_keys(chunk):
                        issue_buckets.setdefault(f"{key}:issue:{issue_key}", []).append(chunk)
                for issue_key, issue_chunks in issue_buckets.items():
                    aggregates[issue_key] = _complaint_stats(issue_chunks)
    return aggregates


def _complaint_stats(chunks: list[dict[str, Any]]) -> dict[str, Any]:
    seen: set[str] = set()
    unique_chunks = []
    for chunk in chunks:
        identity = _chunk_identity(chunk)
        if identity in seen:
            continue
        seen.add(identity)
        unique_chunks.append(chunk)
    dates = sorted(
        str(chunk.get("fields", {}).get("grievance_date", ""))
        for chunk in unique_chunks
        if chunk.get("fields", {}).get("grievance_date")
    )
    status_counts = Counter(
        str(chunk.get("fields", {}).get("status", ""))
        for chunk in unique_chunks
        if chunk.get("fields", {}).get("status")
    )
    return {
        "complaint_count": len(unique_chunks),
        "latest_record_date": dates[-1] if dates else None,
        "status_breakdown": dict(status_counts),
        "example_ids": [
            chunk.get("fields", {}).get("external_complaint_id")
            for chunk in unique_chunks[:5]
            if chunk.get("fields", {}).get("external_complaint_id")
        ],
    }


def _merge_complaint_stats(items: list[dict[str, Any]]) -> dict[str, Any]:
    if not items:
        return {}
    status_counts: Counter[str] = Counter()
    example_ids = []
    latest_dates = []
    total = 0
    for item in items:
        total += int(item.get("complaint_count") or 0)
        latest = item.get("latest_record_date")
        if latest:
            latest_dates.append(str(latest))
        status_counts.update({str(key): int(value) for key, value in dict(item.get("status_breakdown") or {}).items()})
        for example_id in item.get("example_ids") or []:
            if example_id not in example_ids:
                example_ids.append(example_id)
    return {
        "complaint_count": total,
        "latest_record_date": sorted(latest_dates)[-1] if latest_dates else None,
        "status_breakdown": dict(status_counts),
        "example_ids": example_ids[:5],
    }


def _apply_structured_complaint_stats(
    extractive: dict[str, Any],
    stats: dict[str, Any],
    detected_places: list[dict[str, str]],
) -> dict[str, Any]:
    updated = dict(extractive)
    for key in ("complaint_count", "latest_record_date", "status_breakdown", "example_ids"):
        if key in stats:
            updated[key] = stats[key]
    place = _display_place(detected_places, "the matching area")
    parts = []
    if updated.get("complaint_count"):
        parts.append(f"{updated['complaint_count']} matching complaint records for {place}")
    if updated.get("work_payment_count"):
        parts.append(f"{updated['work_payment_count']} matching work/payment rows")
    if updated.get("tender_count"):
        parts.append(f"{updated['tender_count']} matching tender rows")
    if updated.get("streetlight_asset_count"):
        parts.append(f"{updated['streetlight_asset_count']} matching streetlight asset rows")
    if parts:
        updated["summary"] = "Available records found " + ", ".join(parts) + "."
    return updated


def _summary_sentence(
    query: str,
    complaints: list[dict[str, Any]],
    works: list[dict[str, Any]],
    tenders: list[dict[str, Any]],
    streetlights: list[dict[str, Any]],
    detected_places: list[dict[str, str]],
) -> str:
    place = _display_place(detected_places, "the matching area")
    parts = []
    if complaints:
        parts.append(f"{len(complaints)} matching complaint records for {place}")
    if works:
        parts.append(f"{len(works)} matching work/payment rows")
    if tenders:
        parts.append(f"{len(tenders)} matching tender rows")
    if streetlights:
        parts.append(f"{len(streetlights)} matching streetlight asset rows")
    if not parts:
        return f"No row-level evidence matched {query!r}."
    return "Available records found " + ", ".join(parts) + "."


def _civic_triage(
    query: str,
    intent: dict[str, Any],
    detected_places: list[dict[str, str]],
    extractive: dict[str, Any],
    chunks: list[dict[str, Any]],
    gaps: list[str],
    freshness: dict[str, Any],
) -> dict[str, Any]:
    place = _display_place(detected_places, "this area")
    issue = _issue_label(query)
    complaint_examples = [
        str(chunk.get("fields", {}).get("external_complaint_id"))
        for chunk in chunks
        if chunk.get("chunk_type") == "complaint" and chunk.get("fields", {}).get("external_complaint_id")
    ][:5]
    money_examples = [chunk["text"] for chunk in chunks if chunk.get("chunk_type") in {"work_payment", "tender"}][:3]
    routed_roles = _routed_roles(chunks)
    who_to_contact = _who_to_contact(intent, issue, place, routed_roles)
    what_to_do_next = _what_to_do_next(intent, issue, place, complaint_examples)
    if not detected_places:
        what_to_do_next.insert(0, "Please clarify the place before treating these as local records.")
    cause_boundary = (
        f"I cannot prove the exact cause of the {issue} from these records. "
        "The evidence can show complaint history, official statuses, related assets, and related works or payments."
    )
    known = [extractive["summary"]]
    if not detected_places:
        known.insert(0, "No place was confidently detected, so this is not a local answer yet.")
    if complaint_examples:
        known.append(f"Example complaint IDs: {', '.join(complaint_examples)}.")
    if freshness.get("latest_record_date"):
        known.append(f"Latest retrieved complaint record: {freshness['latest_record_date']}.")
    evidence_library = _evidence_library(chunks, query, detected_places, intent)
    issue_tracks = _issue_tracks(intent, chunks, evidence_library, detected_places)
    return {
        "civic_interpretation": _civic_interpretation(issue, place, extractive, detected_places),
        "what_i_can_say": " ".join(known),
        "complaint_memory": {
            "count": extractive["complaint_count"],
            "latest_record_date": extractive["latest_record_date"],
            "status_breakdown": extractive["status_breakdown"],
            "example_ids": complaint_examples,
            "scope_note": (
                "Area/ward-level historical memory; no exact landmark-level match was found."
                if _landmark_terms(query, detected_places)
                else "Area/ward-level historical memory."
            ),
        },
        "who_to_contact": who_to_contact,
        "related_work_and_money_trail": money_examples,
        "evidence_library": evidence_library,
        "issue_tracks": issue_tracks,
        "routed_roles": routed_roles,
        "cause_boundary": cause_boundary,
        "what_to_do_next": what_to_do_next,
        "evidence_gaps": gaps,
    }


def _generated_answer(triage: dict[str, Any], chunks: list[dict[str, Any]], gaps: list[str], freshness: dict[str, Any]) -> str:
    complaint_memory = triage.get("complaint_memory", {})
    status_breakdown = complaint_memory.get("status_breakdown") if isinstance(complaint_memory, dict) else {}
    example_ids = complaint_memory.get("example_ids") if isinstance(complaint_memory, dict) else []
    evidence_library = triage.get("evidence_library", {})
    works = evidence_library.get("work_payments", []) if isinstance(evidence_library, dict) else []
    tenders = evidence_library.get("tenders", []) if isinstance(evidence_library, dict) else []
    complaints = evidence_library.get("complaints", []) if isinstance(evidence_library, dict) else []
    issue_tracks = triage.get("issue_tracks", [])
    lines = [
        str(triage["civic_interpretation"]),
        _format_issue_tracks(issue_tracks) if isinstance(issue_tracks, list) and len(issue_tracks) > 1 else "",
        "Who to contact / call path: Call or file this first: " + " ".join(str(item) for item in triage.get("who_to_contact", [])),
        "What to say when you call: give the nearest landmark, street name, and pole number if visible. Mention recent complaint IDs if you are escalating.",
        (
            "Complaint memory: "
            f"{complaint_memory.get('count', 0) if isinstance(complaint_memory, dict) else 0} matching complaint records; "
            f"latest record {complaint_memory.get('latest_record_date') if isinstance(complaint_memory, dict) else None}; "
            f"status breakdown {status_breakdown or {}}; "
            f"examples {', '.join(example_ids) if example_ids else 'none'}; "
            f"scope {complaint_memory.get('scope_note', 'area/ward-level historical memory') if isinstance(complaint_memory, dict) else 'area/ward-level historical memory'}."
        ),
    ]
    if works or tenders:
        lines.append("Related work and money trail / Related public works and spending: " + " ".join(_format_money_library(works, tenders)))
    else:
        lines.append("Related work and money trail / Related public works and spending: I did not retrieve matching work, tender, or payment rows for this question.")
    lines.append(
        "Public evidence library: "
        + _format_complaint_library(complaints, complaint_memory)
        + " "
        + "The work, payment, and tender entries above are source rows from the public record; they are useful for inspection or escalation."
    )
    lines.append(
        "Neutrality note: These records do not prove corruption, negligence, or the exact cause of this specific issue. "
        "They show what was reported, what was marked in the public record, what work was tendered or paid for, and what remains unclear."
    )
    lines.append(f"What I can say from records: {triage['what_i_can_say']}")
    lines.append(f"What I cannot prove: {triage['cause_boundary']}")
    lines.append("What you can do now: " + " ".join(str(item) for item in triage.get("what_to_do_next", [])))
    if freshness.get("latest_record_date"):
        lines.append(f"Latest retrieved record date: {freshness['latest_record_date']}.")
    if gaps:
        lines.append("Gaps: " + " ".join(gaps))
    return " ".join(line for line in lines if line)


def _answer_brief(
    triage: dict[str, Any],
    extractive: dict[str, Any],
    gaps: list[str],
    freshness: dict[str, Any],
) -> dict[str, Any]:
    complaint_memory = triage.get("complaint_memory") if isinstance(triage.get("complaint_memory"), dict) else {}
    evidence_library = triage.get("evidence_library") if isinstance(triage.get("evidence_library"), dict) else {}
    works = evidence_library.get("work_payments", []) if isinstance(evidence_library, dict) else []
    tenders = evidence_library.get("tenders", []) if isinstance(evidence_library, dict) else []
    complaints = evidence_library.get("complaints", []) if isinstance(evidence_library, dict) else []
    issue_tracks = triage.get("issue_tracks") if isinstance(triage.get("issue_tracks"), list) else []
    count = int(complaint_memory.get("count") or extractive.get("complaint_count") or 0)
    latest = complaint_memory.get("latest_record_date") or freshness.get("latest_record_date")
    example_ids = [str(item) for item in complaint_memory.get("example_ids") or [] if item]
    short_answer = _brief_short_answer(triage, count, latest, bool(works or tenders), bool(gaps))
    records_show = []
    if count:
        records_show.append(
            f"{count} matching historical complaint records were found"
            + (f" through {latest}" if latest else "")
            + "."
        )
    scope_note = complaint_memory.get("scope_note")
    if scope_note:
        records_show.append(str(scope_note))
    for track in issue_tracks:
        title = str(track.get("title") or track.get("issue_key") or "Evidence")
        summary = str(track.get("summary") or "")
        if summary:
            records_show.append(f"{title}: {summary}")
    what_to_cite = []
    if example_ids:
        what_to_cite.append(f"Complaint IDs: {', '.join(example_ids[:5])}.")
    for item in _brief_evidence_rows(works + tenders, limit=2):
        what_to_cite.append(f"{item['kind']}: {item['label']} ({item['source']}).")
    related_works = [
        f"{row['label']} - {row['match_strength']}: {row['match_reason']} [{row['source']}]"
        for row in _brief_evidence_rows(works + tenders, limit=4)
    ]
    if not related_works:
        related_works.append("No matching work, tender, or payment rows were retrieved for this question.")
    limits = [
        "These records do not prove corruption, negligence, or the exact current cause.",
        "Historical closure or registration status is not proof of live repair status.",
    ]
    limits.extend(str(gap) for gap in gaps)
    evidence_table = _brief_evidence_rows(complaints + works + tenders, limit=8)
    return {
        "short_answer": short_answer,
        "records_show": records_show or ["No row-level civic evidence matched this question."],
        "what_to_cite": what_to_cite or ["No specific complaint ID, work order, tender, or payment row was retrieved."],
        "who_to_contact": [str(item) for item in triage.get("who_to_contact", [])],
        "related_works": related_works,
        "limits": _dedupe_strings(limits),
        "evidence_table": evidence_table,
    }


def _brief_short_answer(
    triage: dict[str, Any],
    complaint_count: int,
    latest: str | None,
    has_money: bool,
    has_gaps: bool,
) -> str:
    base = str(triage.get("civic_interpretation") or "I found public civic records related to this question.")
    first_sentence = base.split(". ")[0].strip()
    details = []
    if complaint_count:
        details.append(f"{complaint_count} historical complaint records")
    if has_money:
        details.append("related work/payment or tender rows")
    if latest:
        details.append(f"latest complaint date {latest}")
    suffix = "; ".join(details)
    answer = first_sentence + (f". Records include {suffix}." if suffix else ".")
    if has_gaps:
        answer += " Some evidence is area-level rather than exact-landmark proof."
    return answer[:360].rstrip()


def _brief_evidence_rows(entries: list[dict[str, Any]], limit: int) -> list[dict[str, str]]:
    rows = []
    for entry in entries[:limit]:
        citation = entry.get("citation") if isinstance(entry.get("citation"), dict) else {}
        text = _clean_text(str(entry.get("text", "")))
        label = text[:180] + ("..." if len(text) > 180 else "")
        source = str(citation.get("source_id") or "source row")
        if citation.get("row_number"):
            source += f" row {citation['row_number']}"
        rows.append(
            {
                "kind": _brief_entry_kind(entry),
                "label": label,
                "source": source,
                "match_strength": str(entry.get("match_strength") or "source-backed"),
                "match_reason": str(entry.get("match_reason") or "Retrieved supporting row."),
            }
        )
    return rows


def _brief_entry_kind(entry: dict[str, Any]) -> str:
    fields = entry.get("fields") if isinstance(entry.get("fields"), dict) else {}
    if fields.get("external_complaint_id"):
        return "Complaint"
    if any(str(key).lower() in {"tender number", "tender_number"} for key in fields):
        return "Tender"
    return "Work/payment"


def _dedupe_strings(items: list[str]) -> list[str]:
    seen = set()
    deduped = []
    for item in items:
        text = str(item).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        deduped.append(text)
    return deduped


def _civic_interpretation(issue: str, place: str, extractive: dict[str, Any], detected_places: list[dict[str, str]]) -> str:
    if not detected_places:
        return (
            "I need a clearer place before this becomes a local civic answer. "
            "The records below are broader context, not proof about your exact street."
        )
    complaint_count = int(extractive.get("complaint_count") or 0)
    work_count = int(extractive.get("work_payment_count") or 0)
    tender_count = int(extractive.get("tender_count") or 0)
    if complaint_count and (work_count or tender_count):
        return (
            f"This looks like a recurring {issue} around {place}, with both complaint history and related public work or spending records. "
            "That is useful escalation context: it suggests the issue is not only a one-off observation, and there are public records you can cite when asking for action."
        )
    if complaint_count:
        return (
            f"This looks like a recurring {issue} around {place}. "
            "The complaint record is the strongest evidence lane here, so the immediate move is to file or escalate with the local complaint history."
        )
    if work_count or tender_count:
        return (
            f"This looks like a public-works trail for {issue} around {place}. "
            "I found related tender, work, or payment records, but little matching complaint memory in the retrieved rows."
        )
    return f"This looks like a {issue} around {place}, but the retrieved public records are thin."


def _evidence_library(
    chunks: list[dict[str, Any]],
    query: str,
    detected_places: list[dict[str, str]],
    intent: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    library = {"complaints": [], "work_payments": [], "tenders": [], "assets": []}
    for chunk in chunks:
        strength, reason = _match_strength(chunk, query, detected_places, intent)
        entry = {
            "text": _public_text(str(chunk.get("text", ""))),
            "fields": chunk.get("fields", {}),
            "citation": chunk.get("citation", {}),
            "match_strength": strength,
            "match_reason": reason,
        }
        chunk_type = chunk.get("chunk_type")
        if chunk_type == "complaint":
            library["complaints"].append(entry)
        elif chunk_type == "work_payment":
            library["work_payments"].append(entry)
        elif chunk_type == "tender":
            library["tenders"].append(entry)
        elif chunk_type == "streetlight_asset":
            library["assets"].append(entry)
    return {key: value[:5] for key, value in library.items()}


def _issue_tracks(
    intent: dict[str, Any],
    chunks: list[dict[str, Any]],
    evidence_library: dict[str, list[dict[str, Any]]],
    detected_places: list[dict[str, str]],
) -> list[dict[str, Any]]:
    tracks = []
    place_note = "area/ward-level" if detected_places else "citywide/source-level"
    for issue_key in _intent_issue_keys(intent):
        issue_chunks = [chunk for chunk in chunks if issue_key in _chunk_issue_keys(_index_chunk(chunk))]
        complaint_examples = [
            str(chunk.get("fields", {}).get("external_complaint_id"))
            for chunk in issue_chunks
            if chunk.get("chunk_type") == "complaint" and chunk.get("fields", {}).get("external_complaint_id")
        ][:3]
        support_types = sorted({str(chunk.get("chunk_type")) for chunk in issue_chunks})
        if issue_chunks:
            summary = f"{len(issue_chunks)} retrieved supporting rows at {place_note} scope."
        else:
            summary = "No row-level example was retrieved for this evidence lane."
        gap = None
        if detected_places:
            gap = "No exact landmark-level match was found; treat this as area/ward-level evidence."
        tracks.append(
            {
                "issue_key": issue_key,
                "title": _issue_track_title(issue_key),
                "summary": summary,
                "complaint_example_ids": complaint_examples,
                "support_types": support_types,
                "gap": gap,
            }
        )
    return tracks


def _issue_track_title(issue_key: str) -> str:
    return {
        "streetlight": "Streetlight evidence",
        "drain": "Flooding / drain evidence",
        "garbage": "Garbage evidence",
        "road": "Road evidence",
    }.get(issue_key, "Civic evidence")


def _format_issue_tracks(issue_tracks: list[dict[str, Any]]) -> str:
    parts = []
    for track in issue_tracks:
        examples = track.get("complaint_example_ids") or []
        sentence = f"{track.get('title')}: {track.get('summary')}"
        if examples:
            sentence += f" Example complaint IDs: {', '.join(str(item) for item in examples[:3])}."
        if track.get("gap"):
            sentence += f" {track['gap']}"
        parts.append(sentence)
    return " ".join(parts)


def _match_strength(
    chunk: dict[str, Any],
    query: str,
    detected_places: list[dict[str, str]],
    intent: dict[str, Any],
) -> tuple[str, str]:
    text = normalize_name(f"{chunk.get('title', '')} {chunk.get('text', '')}")
    landmark_terms = _landmark_terms(query, detected_places)
    has_landmark = any(term in text for term in landmark_terms)
    chunk_issues = _chunk_issue_keys(_index_chunk(chunk))
    requested_issues = set(_intent_issue_keys(intent))
    has_issue = bool(chunk_issues & requested_issues) if requested_issues else False
    has_place = bool(detected_places)
    if has_landmark and has_issue:
        return "strong", "Matched the issue and the named landmark."
    if has_issue and has_place:
        return "area/ward-level", "Matched the issue and place/ward, but not the exact landmark."
    if has_place:
        return "weak-area-context", "Matched the place/ward, but issue linkage is weaker."
    if has_issue:
        return "issue-only", "Matched the issue without a confident place."
    return "source-context", "Retrieved as broader context, not a direct local match."


def _landmark_terms(query: str, detected_places: list[dict[str, str]]) -> list[str]:
    ignored = {
        "near",
        "road",
        "after",
        "rain",
        "show",
        "complaint",
        "history",
        "related",
        "work",
        "orders",
        "payments",
        "calling",
        "contact",
        "first",
        "claim",
        "records",
        "gaps",
        "live",
        "streetlights",
        "streetlight",
        "failing",
        "floods",
        "bridge",
    }
    for place in detected_places:
        for key in ("normalized_name", "ward_name"):
            ignored.update(normalize_name(str(place.get(key, ""))).split())
    return [
        term
        for term in _query_terms(query)
        if len(term) >= 5 and term not in ignored and term not in {"bellandur", "bellanduru"}
    ]


def _format_complaint_library(complaints: list[dict[str, Any]], complaint_memory: dict[str, Any]) -> str:
    if not complaints:
        return "Complaint history: no matching complaint examples were retrieved."
    examples = []
    for complaint in complaints[:3]:
        fields = complaint.get("fields", {})
        citation = complaint.get("citation", {})
        examples.append(
            f"{fields.get('external_complaint_id')} on {fields.get('grievance_date')} "
            f"status {fields.get('status')} "
            f"[{citation.get('source_id')} row {citation.get('row_number')}]"
        )
    return "Complaint history: " + "; ".join(examples) + "."


def _format_money_library(works: list[dict[str, Any]], tenders: list[dict[str, Any]]) -> list[str]:
    lines = []
    for work in works[:2]:
        fields = work.get("fields", {})
        citation = work.get("citation", {})
        contractor = _first_available_field(fields, "contractor", "Contractor", "Name of contractor")
        amount = _first_available_field(fields, "amount", "Gross", "Tender Value in Rs")
        payment = _first_available_field(fields, "brnumber", "BR Number", "Payment", "BR", "RTGS")
        strength = work.get("match_strength") or "unscored"
        reason = work.get("match_reason") or "No match explanation available."
        lines.append(
            f"Work/payment ({strength}; {reason}): {work.get('text')} "
            f"contractor {contractor or 'not listed'}; amount {amount or 'not listed'}; payment reference {payment or 'not listed'} "
            f"[{citation.get('source_id')} row {citation.get('row_number')}]."
        )
    for tender in tenders[:2]:
        fields = tender.get("fields", {})
        citation = tender.get("citation", {})
        strength = tender.get("match_strength") or "unscored"
        reason = tender.get("match_reason") or "No match explanation available."
        lines.append(
            f"Tender ({strength}; {reason}): {tender.get('text')} tender number {_first_available_field(fields, 'Tender Number') or 'not listed'} "
            f"[{citation.get('source_id')} row {citation.get('row_number')}]."
        )
    return lines


def _first_available_field(fields: dict[str, Any], *keys: str) -> str:
    lowered = {str(key).lower(): str(value) for key, value in fields.items()}
    for key in keys:
        value = lowered.get(key.lower())
        if value and value.strip():
            return value.strip()
    return ""


def _issue_label(query: str) -> str:
    text = query.lower()
    if "street" in text and "light" in text:
        return "streetlight issue"
    if "garbage" in text or "waste" in text:
        return "garbage issue"
    if "drain" in text:
        return "drain issue"
    if "road" in text or "pothole" in text:
        return "road issue"
    return "civic issue"


def _who_to_contact(intent: dict[str, Any], issue: str, place: str, routed_roles: list[str]) -> list[str]:
    roles_text = (
        f" Some historical complaint rows list assigned staff/roles such as: {', '.join(routed_roles[:3])}; use official helplines first because assignments may be stale."
        if routed_roles
        else ""
    )
    issue_keys = set(_intent_issue_keys(intent))
    if "streetlight" in issue:
        contacts = [
            f"Call GBA/BBMP helpline 1533, or file in the Namma Bengaluru (Sahaaya 2.0) app for {place} under a streetlight/electrical complaint category.{roles_text}",
            "If the light failure looks like a power-supply or electrical-safety issue, call BESCOM 1912. BESCOM also lists WhatsApp 9449844640 for complaints.",
        ]
        if issue_keys & {"drain", "road"}:
            contacts.append("For flooding, drains, potholes, or road-engineering issues, file a separate GBA/BBMP complaint under road/drain engineering and ask for AE/AEE routing.")
        return contacts
    if "garbage" in issue:
        return [
            f"Call GBA/BBMP helpline 1533, or file in the Namma Bengaluru (Sahaaya 2.0) app for {place} under Solid Waste Management / garbage complaint categories.{roles_text}",
            "When calling, ask for the complaint to be assigned to the local SWM AEE or health/solid-waste team, and keep the complaint number for escalation.",
        ]
    if "road" in issue or "drain" in issue:
        return [
            f"Call GBA/BBMP helpline 1533, or file in the Namma Bengaluru (Sahaaya 2.0) app for {place} under road, pothole, drain, or engineering complaint categories.{roles_text}",
            "Ask for routing to the ward engineering chain: AE/AEE first, then EE if the complaint is closed without repair.",
        ]
    return [
        f"Call GBA/BBMP helpline 1533, or file in the Namma Bengaluru (Sahaaya 2.0) app for {place}.{roles_text}",
        "Use agency-specific channels if the retrieved record identifies BESCOM, BWSSB, BTP, or another owner.",
    ]


def _routed_roles(chunks: list[dict[str, Any]]) -> list[str]:
    roles = []
    seen = set()
    for chunk in chunks:
        if chunk.get("chunk_type") != "complaint":
            continue
        fields = chunk.get("fields", {})
        role = _clean_text(str(fields.get("staff_name", "")))
        if not role or role.lower() in {"none", "null", "nan"}:
            continue
        if role in seen:
            continue
        roles.append(role)
        seen.add(role)
    return roles


def _what_to_do_next(intent: dict[str, Any], issue: str, place: str, complaint_examples: list[str]) -> list[str]:
    steps = [
        "File a fresh complaint with the nearest landmark, street name, and pole number if visible.",
    ]
    if complaint_examples:
        steps.append(f"Cite nearby historical complaint IDs when escalating: {', '.join(complaint_examples[:3])}.")
    steps.append("Do not treat historical closure or registration status as proof of the current repair state.")
    return steps


def _coverage_gaps(query: str, intent: dict[str, Any], chunks: list[dict[str, Any]], detected: list[dict[str, str]]) -> list[str]:
    gaps = []
    text = query.lower()
    types = {chunk["chunk_type"] for chunk in chunks}
    landmark_terms = _landmark_terms(query, detected)
    if not detected:
        gaps.append("No place was confidently detected; results may be citywide or source-level.")
    if landmark_terms and not any(any(term in normalize_name(f"{chunk.get('title', '')} {chunk.get('text', '')}") for term in landmark_terms) for chunk in chunks):
        gaps.append("No exact landmark-level match was found; evidence is area/ward-level unless a row explicitly names the landmark.")
    if intent["needs_money"] and not ({"work_payment", "tender"} & types):
        gaps.append("No normalized or raw row-level tender/payment evidence matched the query.")
    if intent["needs_money"] and "tender" in text and "tender" not in types:
        gaps.append("No row-level tender evidence matched; retrieved money-trail evidence is limited to work/payment rows.")
    if intent["needs_complaints"] and "complaint" not in types:
        gaps.append("No matching complaint rows were found.")
    if not chunks:
        gaps.append("No row-level evidence matched; source metadata alone is not treated as an answer.")
    return gaps


def _freshness(chunks: list[dict[str, Any]]) -> dict[str, Any]:
    dates = sorted(
        str(chunk.get("fields", {}).get("grievance_date", ""))
        for chunk in chunks
        if chunk.get("fields", {}).get("grievance_date")
    )
    run_ids = sorted({str(chunk.get("citation", {}).get("run_id", "")) for chunk in chunks if chunk.get("citation", {}).get("run_id")})
    return {
        "latest_record_date": dates[-1] if dates else None,
        "source_run_ids": run_ids,
        "note": "No live civic status is claimed unless a retrieved source row explicitly says so.",
    }


def _rank_chunks(chunks: list[dict[str, Any]], query: str, relevant_names: set[str], place_numbers: set[str]) -> list[dict[str, Any]]:
    terms = _query_terms(query)
    query_text = query.lower()
    scored = []
    for chunk in chunks:
        text = f"{chunk.get('title', '')} {chunk.get('text', '')}".lower()
        score = sum(1 for term in terms if term in text)
        if chunk["chunk_type"] == "complaint":
            score += 8
        if chunk["chunk_type"] in {"work_payment", "tender"}:
            score += 6
        if chunk["chunk_type"] == "work_payment" and re.search(r"\b(work orders?|payment|paid|bill|contractor)\b", query_text):
            score += 8
        if chunk["chunk_type"] == "tender" and re.search(r"\b(tender|tenders|procurement)\b", query_text):
            score += 8
        if _row_matches_place(chunk.get("fields", {}), text, relevant_names, place_numbers):
            score += 10
        scored.append((score, chunk))
    return [
        chunk
        for _score, chunk in sorted(
            scored,
            key=lambda item: (-item[0], _descending_date_key(item[1]), item[1].get("source_id", "")),
        )
    ]


def _select_retrieved_chunks(chunks: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    selected_ids: set[str] = set()
    for chunk_type in ("complaint", "work_payment", "tender", "streetlight_asset"):
        chunk = next((item for item in chunks if item.get("chunk_type") == chunk_type), None)
        if chunk:
            selected.append(chunk)
            selected_ids.add(_chunk_identity(chunk))
    for chunk in chunks:
        if len(selected) >= limit:
            break
        identity = _chunk_identity(chunk)
        if identity in selected_ids:
            continue
        selected.append(chunk)
        selected_ids.add(identity)
    return selected


def _chunk_identity(chunk: dict[str, Any]) -> str:
    citation = chunk.get("citation", {})
    return json.dumps(
        [
            chunk.get("chunk_type"),
            citation.get("source_id"),
            citation.get("raw_file"),
            citation.get("row_number"),
        ],
        sort_keys=True,
    )


def _descending_date_key(chunk: dict[str, Any]) -> tuple[int, int, int]:
    value = str(chunk.get("fields", {}).get("grievance_date", ""))
    match = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", value)
    if not match:
        return (0, 0, 0)
    year, month, day = (int(part) for part in match.groups())
    return (-year, -month, -day)


def _matching_run_dirs(raw_root: Path, source_tokens: tuple[str, ...]) -> list[Path]:
    if not raw_root.exists():
        return []
    dirs = []
    for source_dir in sorted(path for path in raw_root.iterdir() if path.is_dir()):
        source_id = source_dir.name.lower()
        if not any(token in source_id for token in source_tokens):
            continue
        latest = _latest_successful_run(source_dir)
        if latest:
            dirs.append(latest)
    return dirs


def _latest_successful_run(source_dir: Path) -> Path | None:
    for run_dir in sorted([path for path in source_dir.iterdir() if path.is_dir()], reverse=True):
        manifest = run_dir / "manifest.json"
        if not manifest.exists():
            continue
        try:
            data = json.loads(manifest.read_text())
        except json.JSONDecodeError:
            continue
        if data.get("status") == "success":
            return run_dir
    return None


def _manifest_csv_files(run_dir: Path) -> list[Path]:
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.exists():
        return []
    try:
        manifest = json.loads(manifest_path.read_text())
    except json.JSONDecodeError:
        return []
    files = manifest.get("files", [])
    paths = []
    if isinstance(files, list):
        for item in files:
            if isinstance(item, dict) and isinstance(item.get("path"), str):
                path = run_dir / item["path"]
                if path.suffix.lower() == ".csv" and path.exists():
                    paths.append(path)
    if not paths:
        paths = sorted((run_dir / "original").glob("*.csv"))
    return paths


def _read_csv_rows(path: Path) -> list[tuple[int, dict[str, str]]]:
    for encoding in ("utf-8-sig", "latin-1"):
        try:
            with path.open(newline="", encoding=encoding) as handle:
                reader = csv.DictReader(handle)
                if not reader.fieldnames:
                    return []
                return [
                    (row_number, {str(key): str(value or "") for key, value in row.items() if key is not None})
                    for row_number, row in enumerate(reader, start=2)
                ]
        except UnicodeDecodeError:
            continue
    return []


def _read_json_list(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    data = json.loads(path.read_text())
    if not isinstance(data, list):
        raise ValueError(f"{path} must contain a JSON list")
    return [item for item in data if isinstance(item, dict)]


def _relevant_place_names(detected: list[dict[str, str]], mappings: list[dict[str, Any]]) -> set[str]:
    names = set()
    for place in detected:
        for value in (place.get("normalized_name", ""), place.get("ward_name", "")):
            normalized = normalize_name(value)
            if normalized:
                names.add(normalized)
                names.add(_without_terminal_u(normalized))
    for mapping in mappings:
        old_name = normalize_name(str(mapping.get("old_ward_name", "")))
        new_name = normalize_name(str(mapping.get("new_ward_name", "")))
        if names & {old_name, new_name, _without_terminal_u(old_name), _without_terminal_u(new_name)}:
            for value in (old_name, new_name):
                if value:
                    names.add(value)
                    names.add(_without_terminal_u(value))
    return {name for name in names if name}


def _relevant_ward_numbers(detected: list[dict[str, str]], mappings: list[dict[str, Any]]) -> set[str]:
    numbers = {str(place.get("ward_number", "")).strip() for place in detected if place.get("ward_number")}
    for mapping in mappings:
        if numbers & {str(mapping.get("old_ward_number", "")).strip(), str(mapping.get("new_ward_number", "")).strip()}:
            numbers.add(str(mapping.get("old_ward_number", "")).strip())
            numbers.add(str(mapping.get("new_ward_number", "")).strip())
    return {number for number in numbers if number}


def _row_matches_place(row: dict[str, Any], row_text: str, relevant_names: set[str], place_numbers: set[str]) -> bool:
    text = normalize_name(row_text)
    for name in relevant_names:
        if name and _contains_phrase(text, name):
            return True
    row_values = {normalize_name(str(value)) for value in row.values()}
    if row_values & relevant_names:
        return True
    for key, value in row.items():
        if str(key).lower() in {"ward", "ward_no", "ward no", "ward number", "ward_no_name"}:
            if str(value).strip() in place_numbers:
                return True
    if place_numbers:
        for number in place_numbers:
            if re.search(rf"\bward\s*(no\.?|number)?\s*-?\s*{re.escape(number)}\b", row_text, re.IGNORECASE):
                return True
    return False


def _row_matches_terms(row_text: str, query: str) -> bool:
    text = normalize_name(row_text)
    terms = [term for term in _query_terms(query) if term not in {"is", "also", "the", "and", "not"}]
    return any(term in text for term in terms)


def _issue_terms(query: str) -> list[str]:
    issue_keys = _query_issue_keys(query)
    terms = []
    if "streetlight" in issue_keys:
        terms.extend(["street light", "streetlight", "electrical"])
    if "garbage" in issue_keys:
        terms.extend(["garbage", "solid waste", "swm"])
    if "drain" in issue_keys:
        terms.append("drain")
    if "road" in issue_keys:
        terms.extend(["road", "pothole"])
    return terms


def _money_context_terms(query: str) -> list[str]:
    issue_keys = _query_issue_keys(query)
    if "streetlight" in issue_keys:
        return ["street light", "street lights", "streetlight", "streetlights", "electrical"]
    if "garbage" in issue_keys:
        return ["garbage", "solid waste", "swm", "waste"]
    if "drain" in issue_keys:
        return ["drain", "drains", "swd", "storm water"]
    if "road" in issue_keys:
        return ["road", "roads", "pothole"]
    return []


def _matches_any(value: str, terms: list[str]) -> bool:
    normalized = normalize_name(value)
    return any(normalize_name(term) in normalized for term in terms if term)


def _query_terms(query: str) -> list[str]:
    return [term for term in normalize_name(query).split() if len(term) > 1]


def _contains_phrase(text: str, phrase: str) -> bool:
    if not phrase:
        return False
    return bool(re.search(rf"(^|\s){re.escape(phrase)}($|\s)", text))


def _without_terminal_u(value: str) -> str:
    return value[:-1] if value.endswith("u") and len(value) > 4 else value


def _canonical_place_name(value: str) -> str:
    normalized = normalize_name(value)
    if normalized == "bellanduru":
        return "bellandur"
    return _without_terminal_u(normalized)


def _display_place(detected_places: list[dict[str, str]], fallback: str) -> str:
    if not detected_places:
        return fallback
    normalized = _canonical_place_name(str(detected_places[0].get("normalized_name", "")))
    if normalized:
        return normalized.replace("_", " ").title()
    return _public_text(str(detected_places[0].get("ward_name", ""))) or fallback


def _public_text(value: str) -> str:
    return re.sub(r"\bBellanduru\b", "Bellandur", str(value))


def _first_value(row: dict[str, str], *keys: str) -> str:
    lower = {key.lower(): value for key, value in row.items()}
    for key in keys:
        value = lower.get(key.lower())
        if value and value.strip():
            return value.strip()
    return ""


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value).replace("</a>", " ")).strip()


def _citation(evidence: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_id": evidence.get("source_id"),
        "run_id": evidence.get("run_id"),
        "raw_file": evidence.get("raw_file"),
        "row_number": evidence.get("row_number"),
    }


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


def _answer_contract_fields(
    query: str,
    intent: dict[str, Any],
    detected_places: list[dict[str, str]],
    extractive: dict[str, Any],
    triage: dict[str, Any],
    citations: list[dict[str, Any]],
    gaps: list[str],
    freshness: dict[str, Any],
    indexed_chunks: Any,
    loaded_index_path: Path | None,
    timings: dict[str, float],
) -> dict[str, Any]:
    contract_citations = _contract_citations(citations, triage)
    claims = _contract_claims(query, intent, extractive, triage, freshness, gaps, contract_citations)
    return {
        "question": query,
        "normalized_place": detected_places[0]["normalized_name"] if detected_places else None,
        "normalized_issue": _normalized_issue(intent, query),
        "answer_type": _answer_type(extractive, gaps),
        "confidence_label": _confidence_label(detected_places, extractive, gaps),
        "jurisdiction": _jurisdiction(detected_places, triage, contract_citations),
        "claims": claims,
        "citations": contract_citations,
        "what_to_do_next": triage.get("what_to_do_next", []),
        "retrieval_trace": {
            "retrieval_snapshot_id": _retrieval_snapshot_id(indexed_chunks, loaded_index_path),
            "retrieval_backend": _retrieval_backend(indexed_chunks),
            "stage_timings_ms": {key: round(value * 1000, 3) for key, value in timings.items()},
            "retrieved_chunk_count": int(
                extractive.get("complaint_count", 0) or 0
            ),
        },
    }


def _contract_citations(citations: list[dict[str, Any]], triage: dict[str, Any]) -> list[dict[str, Any]]:
    contract = []
    for index, citation in enumerate(citations, start=1):
        item = dict(citation)
        item["id"] = f"c{index}"
        item.setdefault("source_tier", 1)
        contract.append(item)
    if triage.get("who_to_contact"):
        contract.append(
            {
                "id": f"c{len(contract) + 1}",
                "source_id": "official_contact_channels",
                "source_tier": 1,
                "evidence_type": "contact_channel",
                "citation": {
                    "bbmp_gba_helpline": "1533",
                    "sahaaya": "Namma Bengaluru (Sahaaya 2.0)",
                    "bescom_helpline": "1912",
                    "bescom_whatsapp": "9449844640",
                },
            }
        )
    if not contract:
        contract.append(
            {
                "id": "c1",
                "source_id": "retrieval_system",
                "source_tier": 0,
                "evidence_type": "coverage_gap",
                "citation": {"note": "No row-level evidence was retrieved."},
            }
        )
    return contract


def _contract_claims(
    query: str,
    intent: dict[str, Any],
    extractive: dict[str, Any],
    triage: dict[str, Any],
    freshness: dict[str, Any],
    gaps: list[str],
    citations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    first = citations[0]["id"]
    contact = citations[-1]["id"]
    claims = []
    if extractive.get("complaint_count"):
        claims.append(
            {
                "text": (
                    f"Official records show {extractive['complaint_count']} matching complaint records"
                    + (f" through {extractive['latest_record_date']}" if extractive.get("latest_record_date") else "")
                    + "."
                ),
                "claim_type": "complaint_memory",
                "citation_ids": [first],
                "support_level": "derived",
            }
        )
    if extractive.get("work_payment_count") or extractive.get("tender_count"):
        claims.append(
            {
                "text": (
                    f"Retrieved evidence includes {extractive.get('work_payment_count', 0)} work/payment rows "
                    f"and {extractive.get('tender_count', 0)} tender rows."
                ),
                "claim_type": "money_trail",
                "citation_ids": [first],
                "support_level": "context",
            }
        )
    elif intent.get("needs_money"):
        claims.append(
            {
                "text": "No matching work/payment or tender row was retrieved for this money-trail request.",
                "claim_type": "money_trail",
                "citation_ids": [first],
                "support_level": "gap",
            }
        )
    if triage.get("who_to_contact"):
        claims.append(
            {
                "text": "The answer includes official complaint/contact channels and local routed roles where records show them.",
                "claim_type": "contact",
                "citation_ids": [contact],
                "support_level": "context",
            }
        )
    if freshness.get("latest_record_date"):
        claims.append(
            {
                "text": f"The latest cited complaint record date is {freshness['latest_record_date']}.",
                "claim_type": "freshness",
                "citation_ids": [first],
                "support_level": "derived",
            }
        )
    elif re.search(r"\b(live|current|today|status|fresh|latest)\b", query.lower()):
        claims.append(
            {
                "text": "No live/current row-level status was retrieved for this query.",
                "claim_type": "freshness",
                "citation_ids": [first],
                "support_level": "gap",
            }
        )
    for gap in gaps:
        claims.append(
            {
                "text": gap,
                "claim_type": "gap",
                "citation_ids": [first],
                "support_level": "gap",
            }
        )
    if not claims:
        claims.append(
            {
                "text": "No row-level evidence matched this query.",
                "claim_type": "gap",
                "citation_ids": [first],
                "support_level": "gap",
            }
        )
    return claims


def _normalized_issue(intent: dict[str, Any], query: str) -> str:
    keys = intent.get("issue_keys")
    if isinstance(keys, list) and keys:
        for preferred in ("streetlight", "garbage", "drain", "road"):
            if preferred in keys:
                return preferred
    return normalize_name(_issue_label(query)).replace(" issue", "") or "civic"


def _answer_type(extractive: dict[str, Any], gaps: list[str]) -> str:
    if extractive.get("complaint_count"):
        return "historical_memory"
    if extractive.get("work_payment_count") or extractive.get("tender_count"):
        return "official_record"
    if gaps:
        return "insufficient_evidence"
    return "route_to_authority"


def _confidence_label(detected_places: list[dict[str, str]], extractive: dict[str, Any], gaps: list[str]) -> str:
    if not detected_places:
        return "needs_place_clarification"
    if gaps:
        return "partial"
    if extractive.get("complaint_count") or extractive.get("work_payment_count") or extractive.get("tender_count"):
        return "source_backed"
    return "thin"


def _jurisdiction(
    detected_places: list[dict[str, str]],
    triage: dict[str, Any],
    citations: list[dict[str, Any]],
) -> dict[str, Any]:
    place = detected_places[0] if detected_places else {}
    return {
        "agency": "GBA/BBMP",
        "ward": _display_place(detected_places, "") if detected_places else None,
        "ward_number": place.get("ward_number"),
        "normalized_place": place.get("normalized_name"),
        "confidence": 0.9 if detected_places else 0.0,
        "match_method": "ward_alias" if detected_places else "none",
        "routed_roles": triage.get("routed_roles", []),
        "citation_ids": [citations[-1]["id"]] if citations else [],
    }


def _retrieval_snapshot_id(indexed_chunks: Any, loaded_index_path: Path | None) -> str:
    if isinstance(indexed_chunks, dict):
        built_at = indexed_chunks.get("built_at")
        if built_at:
            return f"rag-index:{built_at}"
    return f"warehouse-fallback:{loaded_index_path}" if loaded_index_path else "warehouse-fallback"


def _retrieval_backend(indexed_chunks: Any) -> str:
    if isinstance(indexed_chunks, dict):
        return str(indexed_chunks.get("storage", "indexed"))
    if isinstance(indexed_chunks, list):
        return "in_memory_index"
    return "warehouse_scan"


def _validate_answer_contract(payload: dict[str, Any]) -> None:
    claims = payload.get("claims")
    if not isinstance(claims, list):
        raise ValueError("AnswerPayload claims must be a list")
    citation_ids = {citation.get("id") for citation in payload.get("citations", []) if isinstance(citation, dict)}
    for claim in claims:
        if not isinstance(claim, dict):
            raise ValueError("AnswerPayload claim must be an object")
        ids = claim.get("citation_ids")
        if not isinstance(ids, list) or not ids:
            raise ValueError(f"Claim is missing citations: {claim}")
        if any(citation_id not in citation_ids for citation_id in ids):
            raise ValueError(f"Claim cites unknown citations: {claim}")


def _default_index_path(warehouse: Path, index_path: Path | str | None) -> Path | None:
    if index_path is not None:
        return Path(index_path)
    default_path = warehouse / DEFAULT_RAG_INDEX_NAME
    return default_path if default_path.exists() else None


def _index_chunk(chunk: dict[str, Any]) -> dict[str, Any]:
    indexed = dict(chunk)
    fields = indexed.get("fields") if isinstance(indexed.get("fields"), dict) else {}
    indexed["search_text"] = normalize_name(
        " ".join(
            [
                str(indexed.get("title", "")),
                str(indexed.get("text", "")),
                " ".join(str(value) for value in fields.values()),
            ]
        )
    )
    return indexed
