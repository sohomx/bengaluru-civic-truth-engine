from __future__ import annotations

import csv
import json
import re
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any

from civic_data.safety import redact_pii


WARD_SOURCES = {
    "bbmp_ward_information",
    "gba_wards_delimitation_2025",
    "bbmp_ward_wise_public_goods_data",
    "bengaluru_bbmp_ward_details",
}
GRIEVANCE_SOURCES = {"bbmp_grievances_data"}
WORK_PAYMENT_SOURCES = {
    "bbmp_work_orders_and_payments_2025_26",
    "bbmp_work_orders_and_bill_payment",
    "bbmp_work_orders_payments_2025_26",
    "bbmp_work_orders_bill_payment",
}
CHANNEL_SOURCES = {
    "bescom_official_contact_complaint_channels",
    "bwssb_crm_complaint_form",
    "bbmp_swm_legacy",
    "bbmp_swm_infrastructure",
    "bbmp_solid_waste_management_data",
    "bengaluru_traffic_police_official_website",
}


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


def normalize_works_payments(raw_root: Path, warehouse_root: Path) -> dict[str, int]:
    warehouse_root.mkdir(parents=True, exist_ok=True)
    works: dict[str, dict[str, Any]] = {}
    payments: dict[str, dict[str, Any]] = {}
    rejected: list[dict[str, Any]] = []

    for source_id in sorted(WORK_PAYMENT_SOURCES):
        run_dir = latest_successful_run(raw_root / source_id)
        if run_dir is None:
            continue
        for file_path in _manifest_csv_files(run_dir):
            for row_number, row in _read_csv_rows(file_path):
                try:
                    work, payment = _work_payment_records(source_id, run_dir, file_path, row_number, row)
                    works.setdefault(str(work["work_id"]), work)
                    if payment:
                        payments.setdefault(str(payment["payment_id"]), payment)
                except ValueError as exc:
                    rejected.append(_rejection(source_id, file_path, row_number, str(exc), row))

    _write_json(warehouse_root / "works.json", sorted(works.values(), key=lambda item: str(item["work_id"])))
    _write_json(warehouse_root / "payments.json", sorted(payments.values(), key=lambda item: str(item["payment_id"])))
    _write_json(warehouse_root / "work_payment_rejections.json", rejected)
    return {"works": len(works), "payments": len(payments), "rejected": len(rejected)}


def normalize_channels(raw_root: Path, warehouse_root: Path) -> dict[str, int]:
    warehouse_root.mkdir(parents=True, exist_ok=True)
    agencies: dict[str, dict[str, Any]] = {}
    complaint_channels: dict[str, dict[str, Any]] = {}
    contact_channels: dict[str, dict[str, Any]] = {}
    categories: dict[str, dict[str, Any]] = {}
    rejected: list[dict[str, Any]] = []

    for source_id in sorted(CHANNEL_SOURCES):
        run_dir = latest_successful_run(raw_root / source_id)
        if run_dir is None:
            continue
        for file_path in _manifest_files(run_dir, {".html", ".htm", ".txt", ".json"}):
            try:
                records = _channel_records(source_id, run_dir, file_path)
                if not records:
                    continue
                agency = records["agency"]
                agencies.setdefault(str(agency["agency_id"]), agency)
                for channel in records["complaint_channels"]:
                    complaint_channels.setdefault(str(channel["channel_id"]), channel)
                    for issue_type in channel.get("issue_types", []):
                        categories.setdefault(
                            str(issue_type),
                            {
                                "name": str(issue_type),
                                "normalized_name": normalize_name(str(issue_type)),
                                "source_id": source_id,
                                **_claim_metadata(
                                    source_id=source_id,
                                    run_dir=run_dir,
                                    file_path=file_path,
                                    parser_version="channels_v1",
                                    claim_class="official_channel",
                                    allowed_claims=["This public source describes an official filing or contact channel."],
                                    disallowed_claims=["Does not prove individual complaint status or ground resolution."],
                                    freshness_basis="fetched_at",
                                ),
                            },
                        )
                for channel in records["contact_channels"]:
                    contact_channels.setdefault(str(channel["channel_id"]), channel)
            except ValueError as exc:
                rejected.append(_rejection(source_id, file_path, 1, str(exc), {}))

    _write_json(warehouse_root / "agencies.json", sorted(agencies.values(), key=lambda item: str(item["agency_id"])))
    _write_json(
        warehouse_root / "complaint_channels.json",
        sorted(complaint_channels.values(), key=lambda item: str(item["channel_id"])),
    )
    _write_json(
        warehouse_root / "contact_channels.json",
        sorted(contact_channels.values(), key=lambda item: str(item["channel_id"])),
    )
    _write_json(
        warehouse_root / "issue_categories.json",
        sorted(categories.values(), key=lambda item: str(item["normalized_name"])),
    )
    _write_json(warehouse_root / "channel_rejections.json", rejected)
    return {
        "agencies": len(agencies),
        "complaint_channels": len(complaint_channels),
        "contact_channels": len(contact_channels),
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
    return _manifest_files(run_dir, {".csv"})


def _manifest_files(run_dir: Path, suffixes: set[str]) -> list[Path]:
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
        if path.suffix.lower() in suffixes and path.exists():
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
        **_claim_metadata(
            source_id=source_id,
            run_dir=run_dir,
            file_path=file_path,
            parser_version="wards_v2",
            claim_class="proof_with_mirror_caveat",
            allowed_claims=["This row maps old and new ward fields according to the source record."],
            disallowed_claims=["Does not prove legally binding boundary finality without official gazette cross-check."],
            freshness_basis="source_fetched_at",
        ),
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
            "ward_regime": "368_or_369",
            **_claim_metadata(
                source_id=source_id,
                run_dir=run_dir,
                file_path=file_path,
                parser_version="wards_v2",
                claim_class="proof_with_mirror_caveat",
                allowed_claims=["This source maps ward, corporation, assembly, and population fields."],
                disallowed_claims=["Does not prove legally binding boundary finality without official gazette cross-check."],
                freshness_basis="source_fetched_at",
            ),
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
        "ward_regime": "198_or_225_or_243",
        **_claim_metadata(
            source_id=source_id,
            run_dir=run_dir,
            file_path=file_path,
            parser_version="wards_v2",
            claim_class="proof_with_mirror_caveat",
            allowed_claims=["This source maps ward, zone, and constituency fields."],
            disallowed_claims=["Does not prove current GBA filing jurisdiction without a newer lookup or ward-regime match."],
            freshness_basis="source_fetched_at",
        ),
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
        "staff_remarks": redact_pii(row.get("Staff Remarks", "").strip()),
        "staff_name": redact_pii(row.get("Staff Name", "").strip()),
        "evidence": _evidence(source_id, run_dir, file_path, row_number),
        **_claim_metadata(
            source_id=source_id,
            run_dir=run_dir,
            file_path=file_path,
            parser_version="grievances_v2",
            claim_class="reported_civic_need",
            allowed_claims=["This source contains a public grievance row with the listed category/status."],
            disallowed_claims=["Does not prove the issue was actually resolved on the ground."],
            freshness_basis="grievance_date",
        ),
    }


def _work_payment_records(
    source_id: str, run_dir: Path, file_path: Path, row_number: int, row: dict[str, str]
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    external_id = _first_value(row, "id", "Job Number", "Work Order Number", "Work Order No", "Sl No.", "slno")
    description = _clean_htmlish(_first_value(row, "wodetails", "Work Order Details", "Name of Work", "Work Name"))
    if not external_id and not description:
        raise ValueError("work/payment row missing identifier and description")
    source_key = _canonical_work_source_id(source_id)
    work_id = f"{source_key}:{external_id or row_number}"
    ward_number = _first_value(row, "ward", "Ward", "Ward No", "Ward_No")
    contractor = redact_pii(_first_value(row, "contractor", "Contractor"))
    amount = _int_or_none(_first_value(row, "amount", "Total Amount in Rs", "Tender Value in Rs"))
    metadata = _claim_metadata(
        source_id=source_key,
        run_dir=run_dir,
        file_path=file_path,
        parser_version="works_payments_v1",
        claim_class="proof_with_mirror_caveat",
        allowed_claims=["A public work/payment source row exists with these fields."],
        disallowed_claims=["Does not prove field completion, repair quality, corruption, or contractor fault."],
        freshness_basis="source_fetched_at",
    )
    work = {
        "work_id": work_id,
        "source_id": source_key,
        "source_record_id": external_id,
        "ward_number": ward_number,
        "ward_regime": _ward_regime_from_path(file_path),
        "description": redact_pii(description),
        "contractor": contractor,
        "amount": amount,
        "work_order_date": _parse_loose_date(_first_value(row, "Work Order Date")),
        "evidence": _evidence(source_key, run_dir, file_path, row_number),
        **metadata,
    }
    payment_ref = redact_pii(_first_value(row, "brnumber", "BR Number", "Payment", "BR", "RTGS"))
    payment = None
    if payment_ref or _first_value(row, "nett", "Net Payment in Rs ", "Net Payment in Rs"):
        payment = {
            "payment_id": f"{work_id}:payment",
            "work_id": work_id,
            "source_id": source_key,
            "ward_number": ward_number,
            "ward_regime": work["ward_regime"],
            "contractor": contractor,
            "payment_reference": payment_ref,
            "amount": amount,
            "net_amount": _int_or_none(_first_value(row, "nett", "Net Payment in Rs ", "Net Payment in Rs")),
            "deduction": _int_or_none(_first_value(row, "deduction", "Deduction in Rs")),
            "evidence": _evidence(source_key, run_dir, file_path, row_number),
            **metadata,
        }
    return work, payment


def _channel_records(source_id: str, run_dir: Path, file_path: Path) -> dict[str, Any]:
    text = file_path.read_text(errors="ignore")
    normalized = normalize_name(text)
    agency_id = _agency_id_for_source(source_id, normalized)
    if not agency_id:
        raise ValueError("unknown channel agency")
    metadata = _claim_metadata(
        source_id=source_id,
        run_dir=run_dir,
        file_path=file_path,
        parser_version="channels_v1",
        claim_class="official_channel",
        allowed_claims=["This public source describes an official filing or contact channel."],
        disallowed_claims=[
            "Does not prove individual complaint status or ground resolution.",
            "Do not scrape complaint tracking",
            "Do not scrape citizen/account-linked records.",
        ],
        freshness_basis="source_fetched_at",
    )
    issue_types = _issue_types_for_agency(agency_id, normalized)
    agency = {
        "agency_id": agency_id,
        "name": _agency_name(agency_id),
        "source_id": source_id,
        "evidence": _evidence(source_id, run_dir, file_path, 1),
        **metadata,
    }
    complaint_channel = {
        "channel_id": f"{agency_id}:public_complaint_channel",
        "agency_id": agency_id,
        "name": _channel_name(agency_id),
        "url": _source_url_for_channel(source_id),
        "issue_types": issue_types,
        "required_fields_observed": _required_fields(text),
        "evidence": _evidence(source_id, run_dir, file_path, 1),
        **metadata,
    }
    contacts = []
    for value in _public_contact_values(agency_id):
        contacts.append(
            {
                "channel_id": f"{agency_id}:{normalize_name(value).replace(' ', '_')}",
                "agency_id": agency_id,
                "name": value,
                "value": value,
                "channel_type": "public_official_contact",
                "issue_types": issue_types,
                "evidence": _evidence(source_id, run_dir, file_path, 1),
                **metadata,
            }
        )
    return {"agency": agency, "complaint_channels": [complaint_channel], "contact_channels": contacts}


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


def _parse_loose_date(value: str) -> str:
    if not value:
        return ""
    for pattern in (r"\d{4}-\d{2}-\d{2}", r"\d{2}/\d{2}/\d{4}", r"\d{2}-[A-Za-z]{3}-\d{4}"):
        match = re.search(pattern, value)
        if not match:
            continue
        text = match.group(0)
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%b-%Y"):
            try:
                return datetime.strptime(text, fmt).date().isoformat()
            except ValueError:
                continue
    return ""


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


def _claim_metadata(
    *,
    source_id: str,
    run_dir: Path,
    file_path: Path,
    parser_version: str,
    claim_class: str,
    allowed_claims: list[str],
    disallowed_claims: list[str],
    freshness_basis: str,
) -> dict[str, Any]:
    return {
        "source_id": source_id,
        "run_id": run_dir.name,
        "raw_file": str(file_path.relative_to(run_dir)),
        "fetched_at": _fetched_at(run_dir),
        "parser_version": parser_version,
        "claim_class": claim_class,
        "allowed_claims": allowed_claims,
        "disallowed_claims": disallowed_claims,
        "freshness_basis": freshness_basis,
    }


def _fetched_at(run_dir: Path) -> str:
    try:
        manifest = json.loads((run_dir / "manifest.json").read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return run_dir.name
    return str(manifest.get("fetched_at") or run_dir.name)


def _first_value(row: dict[str, str], *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value:
            return str(value).strip()
    return ""


def _clean_htmlish(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value)
    text = text.replace("</a>", " ")
    return " ".join(text.split())


def _canonical_work_source_id(source_id: str) -> str:
    if source_id == "bbmp_work_orders_payments_2025_26":
        return "bbmp_work_orders_and_payments_2025_26"
    if source_id == "bbmp_work_orders_bill_payment":
        return "bbmp_work_orders_and_bill_payment"
    return source_id


def _ward_regime_from_path(path: Path) -> str:
    name = path.name.lower()
    for regime in ("198", "225", "243"):
        if regime in name:
            return regime
    if "common" in name:
        return "common"
    return "unknown"


def _agency_id_for_source(source_id: str, normalized_text: str) -> str:
    if "bwssb" in source_id or "bwssb" in normalized_text:
        return "bwssb"
    if "bescom" in source_id or "bescom" in normalized_text:
        return "bescom"
    if "btp" in source_id or "traffic police" in normalized_text:
        return "btp"
    if "swm" in source_id or "waste" in source_id or "solid waste" in normalized_text:
        return "bswml"
    return ""


def _agency_name(agency_id: str) -> str:
    return {
        "bwssb": "Bengaluru Water Supply and Sewerage Board",
        "bescom": "Bengaluru Electricity Supply Company",
        "btp": "Bengaluru Traffic Police",
        "bswml": "Bengaluru Solid Waste Management Limited / SWM",
    }.get(agency_id, agency_id)


def _channel_name(agency_id: str) -> str:
    return {
        "bwssb": "BWSSB complaint channel",
        "bescom": "BESCOM complaint/contact channel",
        "btp": "Bengaluru Traffic Police public channel",
        "bswml": "BSWML/SWM complaint channel",
    }.get(agency_id, "Public complaint channel")


def _source_url_for_channel(source_id: str) -> str:
    return {
        "bwssb_crm_complaint_form": "https://cms.bwssb.gov.in/module/complain/new_complaint",
        "bescom_official_contact_complaint_channels": "https://bescom.karnataka.gov.in/new-page/Contact%20Us/en",
        "bengaluru_traffic_police_official_website": "https://btp.karnataka.gov.in/en",
    }.get(source_id, "")


def _issue_types_for_agency(agency_id: str, normalized_text: str) -> list[str]:
    if agency_id == "bwssb":
        return ["water", "sewerage", "manhole", "billing"]
    if agency_id == "bescom":
        return ["power", "outage", "electrical_safety", "streetlight"]
    if agency_id == "btp":
        return ["traffic", "road_block", "violation"]
    if agency_id == "bswml":
        return ["garbage", "solid_waste", "blackspot"]
    return ["civic"]


def _required_fields(text: str) -> list[str]:
    labels = []
    for label in ("Consumer Name", "Email Address", "Contact Number", "Address", "Category", "Sub Category", "RR Number"):
        if label.lower() in text.lower():
            labels.append(label)
    return labels


def _public_contact_values(agency_id: str) -> list[str]:
    return {
        "bwssb": ["BWSSB 1916", "BWSSB official call-center email"],
        "bescom": ["BESCOM 1912", "BESCOM official WhatsApp channel"],
        "btp": ["BTP official WhatsApp channel"],
        "bswml": ["GBA/BBMP 1533", "BSWML official WhatsApp channel"],
    }.get(agency_id, [])


def _rejection(
    source_id: str, file_path: Path, row_number: int, reason: str, row: dict[str, str]
) -> dict[str, Any]:
    return {
        "source_id": source_id,
        "raw_file": str(file_path),
        "row_number": row_number,
        "reason": reason,
        "row": {key: redact_pii(value) for key, value in row.items()},
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
