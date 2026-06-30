from __future__ import annotations

import json
import ssl
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from civic_data.normalize import normalize_name


OFFICIAL_XYINFO_PATTERN = "https://gisapi.bbmpgov.in/xyinfo/{lng}/{lat}"
XYINFO_SOURCE_ID = "gba_new_corporation_ward_lookup"


def fetch_xyinfo(lng: float, lat: float) -> dict[str, Any]:
    validate_coordinates(lng=lng, lat=lat)
    url = xyinfo_url(lng, lat)
    request = Request(url, headers={"User-Agent": "bengaluru-civic-truth-engine/0.1"})
    try:
        with urlopen(request, timeout=10) as response:
            body = response.read(65536)
        return {"data": json.loads(body.decode("utf-8")), "tls_verified": True}
    except URLError as exc:
        if "CERTIFICATE_VERIFY_FAILED" not in str(exc):
            raise
        unverified_context = ssl._create_unverified_context()
        with urlopen(request, timeout=10, context=unverified_context) as response:
            body = response.read(65536)
        return {"data": json.loads(body.decode("utf-8")), "tls_verified": False}


def xyinfo_jurisdiction(lng: float, lat: float, response: Any) -> dict[str, Any]:
    payload = response
    tls_verified: bool | None = None
    if isinstance(response, dict) and "data" in response:
        payload = response.get("data")
        tls_verified = response.get("tls_verified") if isinstance(response.get("tls_verified"), bool) else None
    row = xyinfo_first_row(payload)
    new_ward_number, new_ward_name = split_number_name(row.get("New Ward"))
    old_ward_number, old_ward_name = split_number_name(row.get("Old 198 Ward"))
    assembly_number, assembly_name = split_number_name(row.get("Assembly"))
    if not new_ward_number or not new_ward_name:
        raise ValueError("xyinfo response missing New Ward")
    caveat = "Official xyinfo lookup from lat/lng."
    if tls_verified is False:
        caveat += " TLS verification failed in local Python CA store; fetched with endpoint-scoped TLS fallback."
    return {
        "source": "official_xyinfo",
        "source_url": xyinfo_url(lng, lat),
        "official_endpoint_pattern": OFFICIAL_XYINFO_PATTERN,
        "source_id": XYINFO_SOURCE_ID,
        "source_authority": "official",
        "ward_number": new_ward_number,
        "ward_name": new_ward_name,
        "normalized_ward_name": normalize_name(new_ward_name),
        "corporation": str(row.get("Corporation") or ""),
        "zone": str(row.get("Zone") or ""),
        "assembly_constituency": assembly_name or str(row.get("Assembly") or ""),
        "assembly_constituency_number": assembly_number,
        "old_ward_number": old_ward_number,
        "old_ward_name": old_ward_name,
        "ro_division": str(row.get("RO Division") or ""),
        "aro_subdivision": str(row.get("ARO SubDivision") or ""),
        "ward_regime": "live_gba_xyinfo",
        "confidence": 1.0,
        "caveat": caveat,
        "evidence": {
            "source_id": XYINFO_SOURCE_ID,
            "endpoint": xyinfo_url(lng, lat),
            "lat": lat,
            "lng": lng,
        },
    }


def validate_coordinates(*, lng: float, lat: float) -> None:
    if not -180 <= lng <= 180:
        raise ValueError(f"longitude out of range: {lng}")
    if not -90 <= lat <= 90:
        raise ValueError(f"latitude out of range: {lat}")


def xyinfo_url(lng: float, lat: float) -> str:
    return OFFICIAL_XYINFO_PATTERN.format(lng=f"{lng:g}", lat=f"{lat:g}")


def xyinfo_first_row(payload: Any) -> dict[str, Any]:
    if isinstance(payload, list) and payload and isinstance(payload[0], dict):
        return payload[0]
    if isinstance(payload, dict):
        for key in ("data", "results", "features"):
            value = payload.get(key)
            if isinstance(value, list) and value and isinstance(value[0], dict):
                return value[0]
        if "New Ward" in payload:
            return payload
    raise ValueError("xyinfo response did not contain a jurisdiction row")


def split_number_name(value: Any) -> tuple[str, str]:
    text = str(value or "").strip()
    if not text:
        return "", ""
    if " - " in text:
        number, name = text.split(" - ", 1)
        return number.strip(), name.strip()
    match = __import__("re").match(r"^(\d+)\s*[-:]\s*(.+)$", text)
    if match:
        return match.group(1).strip(), match.group(2).strip()
    return "", text
