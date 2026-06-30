from __future__ import annotations

from dataclasses import dataclass

from civic_data.normalize import normalize_name


@dataclass(frozen=True)
class LocalityAliasMatch:
    alias: str
    canonical_ward_name: str
    confidence: float
    caveat: str


LOCALITY_ALIASES: dict[str, tuple[str, float]] = {
    "kadubeesanahalli": ("bellanduru", 0.72),
    "ecospace": ("bellanduru", 0.72),
    "orr bellandur": ("bellanduru", 0.72),
    "outer ring road bellandur": ("bellanduru", 0.72),
    "bellandur outer ring road": ("bellanduru", 0.72),
    "panathur": ("panathur", 0.8),
    "kundalahalli": ("kundalahalli", 0.8),
    "kundalahalli gate": ("kundalahalli", 0.78),
    "itpl": ("whitefield", 0.68),
    "varthur": ("varthur", 0.8),
    "whitefield": ("whitefield", 0.9),
    "mahadevapura": ("mahadevapura", 0.9),
}


def resolve_locality_alias(query: str) -> LocalityAliasMatch | None:
    text = f" {normalize_name(query)} "
    for alias in sorted(LOCALITY_ALIASES, key=len, reverse=True):
        if f" {alias} " in text:
            ward_name, confidence = LOCALITY_ALIASES[alias]
            return LocalityAliasMatch(
                alias=alias,
                canonical_ward_name=ward_name,
                confidence=confidence,
                caveat=(
                    "Text-only locality alias match; this is a confidence hint, not filing-critical proof. "
                    "Confirm with the official lat/lng lookup before filing."
                ),
            )
    return None


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
