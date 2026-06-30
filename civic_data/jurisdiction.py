from __future__ import annotations

from pathlib import Path
from typing import Any, Callable
from urllib.error import URLError

from civic_data.locality import resolve_locality_alias
from civic_data.normalize import normalize_name
from civic_data.warehouse_reader import NormalizedWarehouse
from civic_data.xyinfo import OFFICIAL_XYINFO_PATTERN, XYINFO_SOURCE_ID, fetch_xyinfo, xyinfo_jurisdiction


OFFICIAL_LOOKUP_URL = "https://bbmp.gov.in/KnowYourNewCorporation/index.html"


def resolve_jurisdiction(
    query: str = "",
    *,
    lat: float | None = None,
    lng: float | None = None,
    warehouse_root: Path | str = Path("data/normalized"),
    xyinfo_client: Callable[[float, float], Any] | None = None,
    locality_alias_path: Path | str | None = Path("data/config/locality_aliases.json"),
) -> dict[str, Any]:
    warehouse = NormalizedWarehouse.open(warehouse_root)
    wards = warehouse.load_wards()
    mappings = warehouse.load_old_new_ward_mappings()
    if lat is not None and lng is not None:
        try:
            return xyinfo_jurisdiction(
                lng=lng,
                lat=lat,
                response=(xyinfo_client or fetch_xyinfo)(lng, lat),
            )
        except (ValueError, OSError, TimeoutError, URLError) as exc:
            fallback = _offline_jurisdiction(query, wards, mappings, locality_alias_path=locality_alias_path)
            fallback["official_lookup_error"] = str(exc)
            fallback["caveat"] = (
                "Official xyinfo lookup failed, so this used offline normalized ward data. "
                "Retry xyinfo before filing-critical routing."
            )
            return fallback
    return _offline_jurisdiction(query, wards, mappings, locality_alias_path=locality_alias_path)


def _offline_jurisdiction(
    query: str,
    wards: list[dict[str, Any]],
    mappings: list[dict[str, Any]],
    *,
    locality_alias_path: Path | str | None,
) -> dict[str, Any]:
    match = _match_ward(query, wards, preferred_versions={"gba_2025"})
    if match:
        return _jurisdiction_from_ward(match, source="offline_normalized_wards", confidence=0.95)

    alias = resolve_locality_alias(query, locality_alias_path=locality_alias_path)
    if alias:
        match = _match_ward(alias.canonical_ward_name, wards, preferred_versions={"gba_2025"})
        if match:
            result = _jurisdiction_from_ward(match, source="locality_alias", confidence=alias.confidence)
            result["matched_alias"] = alias.alias
            result["locality_alias_target"] = alias.canonical_ward_name
            result["locality_alias_basis"] = alias.basis
            result["source_url"] = alias.source_url or result["source_url"]
            result["caveat"] = alias.caveat
            return result

    match = _match_mapping(query, wards, mappings) if mappings else None
    if match:
        return _jurisdiction_from_ward(
            match,
            source="offline_normalized_wards_via_old_new_mapping",
            confidence=0.9,
        )

    match = _match_ward(query, wards)
    if match:
        return _jurisdiction_from_ward(match, source="offline_normalized_wards", confidence=0.85)

    return _unresolved(
        "no_offline_ward_match",
        confidence=0.0,
        caveat="No ward/corporation match was found in normalized offline ward data.",
    )


def _jurisdiction_from_ward(match: dict[str, Any], *, source: str, confidence: float) -> dict[str, Any]:
    evidence = match.get("evidence") if isinstance(match.get("evidence"), dict) else {}
    caveat = "Offline ward match. Confirm exact lat/lng against the official GBA/BBMP lookup for filing-critical routing."
    return {
        "source": source,
        "source_url": OFFICIAL_LOOKUP_URL,
        "official_endpoint_pattern": OFFICIAL_XYINFO_PATTERN,
        "source_id": match.get("source_id") or evidence.get("source_id"),
        "source_authority": _source_authority(str(match.get("source_id") or evidence.get("source_id") or "")),
        "ward_number": str(match.get("ward_number") or ""),
        "ward_name": str(match.get("ward_name") or ""),
        "normalized_ward_name": str(match.get("normalized_name") or normalize_name(str(match.get("ward_name") or ""))),
        "corporation": str(match.get("corporation") or ""),
        "zone": str(match.get("zone") or ""),
        "assembly_constituency": str(match.get("assembly_constituency") or ""),
        "ward_regime": str(match.get("ward_regime") or _ward_regime(match)),
        "confidence": confidence,
        "caveat": caveat,
        "evidence": evidence,
    }


def _match_ward(
    query: str,
    wards: list[dict[str, Any]],
    *,
    preferred_versions: set[str] | None = None,
) -> dict[str, Any] | None:
    text = normalize_name(query)
    if not text:
        return None
    exact: list[dict[str, Any]] = []
    fuzzy: list[dict[str, Any]] = []
    for ward in wards:
        normalized = str(ward.get("normalized_name") or normalize_name(str(ward.get("ward_name") or "")))
        if not normalized:
            continue
        aliases = _aliases(normalized)
        if any(_contains_phrase(text, alias) for alias in aliases):
            exact.append(ward)
        elif any(_contains_phrase(text, alias.replace("u", "")) for alias in aliases if alias.replace("u", "")):
            fuzzy.append(ward)
    candidates = exact or fuzzy
    if preferred_versions is not None:
        candidates = [ward for ward in candidates if str(ward.get("version") or "") in preferred_versions]
    if not candidates:
        return None
    return sorted(candidates, key=_ward_match_sort_key)[0]


def _match_mapping(
    query: str,
    wards: list[dict[str, Any]],
    mappings: list[dict[str, Any]],
) -> dict[str, Any] | None:
    text = normalize_name(query)
    if not text:
        return None
    ward_by_name: dict[str, dict[str, Any]] = {}
    for ward in sorted(wards, key=_ward_match_sort_key):
        normalized = str(ward.get("normalized_name") or normalize_name(str(ward.get("ward_name") or "")))
        for alias in _aliases(normalized):
            ward_by_name.setdefault(alias, ward)

    for mapping in mappings:
        names = [
            str(mapping.get("old_ward_name") or ""),
            str(mapping.get("new_ward_name") or ""),
        ]
        if not any(_contains_phrase(text, alias) for name in names for alias in _aliases(normalize_name(name))):
            continue
        new_name = normalize_name(str(mapping.get("new_ward_name") or ""))
        mapped = next((ward_by_name[alias] for alias in _aliases(new_name) if alias in ward_by_name), None)
        if mapped:
            return mapped
    return None


def _ward_match_sort_key(item: dict[str, Any]) -> tuple[int, str]:
    version = str(item.get("version") or "")
    priority = 0 if version == "gba_2025" else 1
    return priority, str(item.get("ward_number") or "")


def _ward_regime(ward: dict[str, Any]) -> str:
    explicit = str(ward.get("ward_regime") or "")
    if explicit:
        return explicit
    if str(ward.get("version") or "") == "gba_2025":
        return "368_or_369"
    if str(ward.get("version") or "") == "old_bbmp":
        return "198_or_225_or_243"
    return "unknown"


def _source_authority(source_id: str) -> str:
    if source_id.startswith(("gba_", "bbmp_")):
        return "mirrored_official"
    return "unknown"


def _unresolved(reason: str, confidence: float, caveat: str) -> dict[str, Any]:
    return {
        "source": reason,
        "source_url": OFFICIAL_LOOKUP_URL,
        "official_endpoint_pattern": OFFICIAL_XYINFO_PATTERN,
        "source_id": "",
        "source_authority": "unknown",
        "ward_number": "",
        "ward_name": "",
        "normalized_ward_name": "",
        "corporation": "",
        "zone": "",
        "assembly_constituency": "",
        "ward_regime": "unknown",
        "confidence": confidence,
        "caveat": caveat,
        "evidence": {},
    }


def _contains_phrase(text: str, phrase: str) -> bool:
    padded_text = f" {text} "
    padded_phrase = f" {phrase} "
    return padded_phrase in padded_text


def _aliases(normalized: str) -> set[str]:
    value = normalize_name(normalized)
    aliases = {value} if value else set()
    if value.endswith("uru") and len(value) > 3:
        aliases.add(value[:-1])
    if value.endswith("u") and len(value) > 3:
        aliases.add(value[:-1])
    if value and not value.endswith("u"):
        aliases.add(f"{value}u")
    return {alias for alias in aliases if alias}
