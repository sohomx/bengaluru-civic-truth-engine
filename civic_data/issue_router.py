from __future__ import annotations

import re
from typing import Any

from civic_data.normalize import normalize_name


AGENCIES: dict[str, dict[str, str]] = {
    "gba": {"agency_id": "gba", "name": "Greater Bengaluru Authority / local city corporation"},
    "bswml": {"agency_id": "bswml", "name": "Bengaluru Solid Waste Management Limited"},
    "bwssb": {"agency_id": "bwssb", "name": "Bengaluru Water Supply and Sewerage Board"},
    "bescom": {"agency_id": "bescom", "name": "Bengaluru Electricity Supply Company"},
    "btp": {"agency_id": "btp", "name": "Bengaluru Traffic Police"},
}


def route_issue(query: str) -> dict[str, Any]:
    text = normalize_name(query)
    issue_type = _issue_type(text)
    if issue_type == "garbage":
        return _route(
            issue_type,
            "bswml",
            "solid_waste_collection",
            "Use BSWML/SWM complaint channels, GBA helpline 1533, or Namma Bengaluru/Sahaaya.",
            ["photo of pileup", "landmark or pin", "date/time", "whether it is recurring"],
            ["private phone numbers", "citizen complaint IDs from private systems"],
            ["No official blackspot is proven unless a public blackspot dataset or record is cited."],
            {"garbage", "solid", "swm", "sweeping", "collection", "blackspot", "dump", "rubbish"},
        )
    if issue_type == "water_sewage":
        return _route(
            issue_type,
            "bwssb",
            "water_or_sewer_service_request",
            "Use BWSSB complaint channels for water, sewage, manholes, billing, or tanker issues.",
            ["photo/video if safe", "address or pin", "RR/account number only in the official BWSSB form"],
            ["RR/account number outside the official BWSSB form", "private complaint tracking details"],
            ["Do not expose account-linked complaint or tracking details."],
            {"sewage", "sewer", "water", "drain", "manhole", "overflow"},
        )
    if issue_type == "power":
        return _route(
            issue_type,
            "bescom",
            "electricity_distribution_safety_or_outage",
            "Use BESCOM 1912, BESCOM online channels, or official WhatsApp channels for outages and electrical safety.",
            ["photo if safe", "pole/transformer identifier if visible", "address or pin"],
            ["private phone numbers", "account numbers outside official BESCOM workflows"],
            ["BESCOM contact guidance does not prove current outage status."],
            {"power", "outage", "transformer", "wire", "wires", "electrical", "sparks", "spark"},
        )
    if issue_type == "traffic":
        route = _route(
            issue_type,
            "btp",
            "traffic_violation_or_disruption",
            "Use Bengaluru Traffic Police channels for traffic violations, diversions, and road-blocking events.",
            ["location", "time", "photo/video if safe", "vehicle number only on official BTP workflows"],
            ["vehicle numbers outside official BTP workflows", "private complainant details"],
            ["BTP advisories do not prove civic repair responsibility."],
            {"traffic", "blocked", "block", "diversion", "advisory"},
        )
        if _has_roadwork_context(text):
            route["secondary_agencies"] = [AGENCIES["gba"]]
            route["dual_path_caveat"] = (
                "Use BTP for the obstruction/traffic safety issue, and GBA/BBMP for the digging, road damage, or civic repair issue."
            )
            route["proof_limitations"].append(
                "Traffic obstruction and civic road repair may have different responsible agencies."
            )
        return route
    if issue_type == "streetlight":
        return _route(
            issue_type,
            "gba",
            "streetlight_maintenance",
            "Use GBA/BBMP local corporation channels for streetlight maintenance; use BESCOM if wording indicates outage, wires, transformer, or power-distribution failure.",
            ["pole number", "photo", "landmark or pin", "whether multiple lights are affected"],
            ["private phone numbers", "claims that a listed work proves the light is fixed"],
            ["Streetlight ownership may split between civic electrical maintenance and BESCOM power distribution."],
            {"street", "light", "lights", "streetlight", "streetlights", "electrical"},
        )
    return _route(
        issue_type,
        "gba",
        "local_civic_issue",
        "Use GBA/BBMP local corporation channels or Namma Bengaluru/Sahaaya for local civic issues.",
        ["photo", "landmark or pin", "date/time", "recurrence details"],
        ["private phone numbers", "uncited claims of official responsibility"],
        ["Routing is an inference until an official complaint channel or record confirms ownership."],
        {"pothole", "potholes", "road", "roads", "asphalt", "maintenance", "footpath", "drain"},
    )


def _route(
    issue_type: str,
    agency_id: str,
    service_type: str,
    filing_guidance: str,
    required_evidence: list[str],
    do_not_include: list[str],
    proof_limitations: list[str],
    match_terms: set[str],
) -> dict[str, Any]:
    return {
        "issue_type": issue_type,
        "agency": AGENCIES[agency_id],
        "open311_like_service_type": service_type,
        "filing_guidance": filing_guidance,
        "required_evidence": required_evidence,
        "do_not_include": do_not_include,
        "proof_limitations": proof_limitations,
        "match_terms": sorted(match_terms),
        "status_policy": "Official closure is a source claim, not verified ground resolution.",
    }


def _issue_type(text: str) -> str:
    if re.search(r"\b(garbage|trash|waste|swm|blackspot|dump|dumped|dumping|debris|rubbish)\b", text):
        return "garbage"
    if re.search(r"\b(sewage|sewer|water|manhole|bwssb|tanker|overflow)\b", text):
        return "water_sewage"
    if re.search(r"\b(power|outage|transformer|wires?|bescom|shock|sparks?|sparking)\b", text):
        return "power"
    if re.search(r"\b(traffic|blocked|diversion|violation|challan|btp)\b", text):
        return "traffic"
    if re.search(r"\b(street\s*lights?|streetlights?|lamp|lamps|pole light|light pole)\b", text):
        return "streetlight"
    if re.search(r"\b(potholes?|roads?|footpath|drain|stormwater|swd)\b", text):
        return "road"
    return "civic"


def _has_roadwork_context(text: str) -> bool:
    return bool(re.search(r"\b(digging|dug|excavation|road\s*work|roadwork|potholes?|road damage|repair)\b", text))
