from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from civic_data.normalize import normalize_name


DEFAULT_LOCALITY_ALIAS_PATH = Path("data/config/locality_aliases.json")


@dataclass(frozen=True)
class LocalityAliasMatch:
    alias: str
    canonical_ward_name: str
    confidence: float
    basis: str
    caveat: str
    source_url: str


def resolve_locality_alias(
    query: str,
    *,
    locality_alias_path: Path | str | None = DEFAULT_LOCALITY_ALIAS_PATH,
) -> LocalityAliasMatch | None:
    text = f" {normalize_name(query)} "
    for match in sorted(load_locality_aliases(locality_alias_path), key=lambda item: len(item.alias), reverse=True):
        if f" {match.alias} " in text:
            return match
    return None


def load_locality_aliases(path: Path | str | None = DEFAULT_LOCALITY_ALIAS_PATH) -> list[LocalityAliasMatch]:
    if path is None:
        return []
    alias_path = Path(path)
    if not alias_path.exists():
        return []
    try:
        parsed = json.loads(alias_path.read_text())
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(parsed, list):
        return []
    aliases = []
    for item in parsed:
        alias = _alias_from_item(item)
        if alias is not None:
            aliases.append(alias)
    return aliases


def _alias_from_item(item: Any) -> LocalityAliasMatch | None:
    if not isinstance(item, dict):
        return None
    alias = normalize_name(str(item.get("alias") or ""))
    ward_name = normalize_name(str(item.get("canonical_ward_name") or ""))
    if not alias or not ward_name:
        return None
    try:
        confidence = float(item.get("confidence"))
    except (TypeError, ValueError):
        return None
    if not 0 <= confidence <= 1:
        return None
    return LocalityAliasMatch(
        alias=alias,
        canonical_ward_name=ward_name,
        confidence=confidence,
        basis=str(item.get("basis") or ""),
        caveat=str(item.get("caveat") or "Text-only locality alias match; confirm with the official lookup before filing."),
        source_url=str(item.get("source_url") or ""),
    )


def place_terms(query: str) -> list[str]:
    words = normalize_name(query).split()
    if not words:
        return []
    stop = _PLACE_STOP_WORDS | _ISSUE_WORDS
    places: list[str] = []
    for index, word in enumerate(words):
        if word not in {"near", "in", "at", "around", "on"}:
            continue
        phrase: list[str] = []
        for candidate in words[index + 1 : index + 4]:
            if candidate in stop:
                break
            phrase.append(candidate)
        if phrase:
            places.append(" ".join(phrase))
    prefix: list[str] = []
    for word in words:
        if word in _ISSUE_WORDS or word in _PLACE_STOP_WORDS:
            break
        prefix.append(word)
    if prefix:
        places.append(" ".join(prefix[:3]))
    result: list[str] = []
    for place in places:
        if place and place not in result and place not in stop and not any(word in stop for word in place.split()):
            result.append(place)
    return result


def first_place_guess(query: str) -> str:
    terms = place_terms(query)
    return terms[0] if terms else ""


_PLACE_STOP_WORDS = {
    "what",
    "who",
    "why",
    "where",
    "there",
    "is",
    "a",
    "an",
    "the",
    "this",
    "that",
    "my",
    "your",
    "can",
    "cite",
    "contact",
    "message",
    "not",
    "working",
    "keeps",
    "recurring",
    "again",
    "main",
    "road",
}
_ISSUE_WORDS = {
    "garbage",
    "trash",
    "waste",
    "swm",
    "blackspot",
    "dump",
    "sewage",
    "sewer",
    "water",
    "manhole",
    "power",
    "outage",
    "transformer",
    "wire",
    "wires",
    "traffic",
    "blocked",
    "diversion",
    "streetlight",
    "streetlights",
    "street",
    "light",
    "lights",
    "lamp",
    "pole",
    "pothole",
    "potholes",
    "footpath",
    "drain",
    "stormwater",
    "swd",
}
