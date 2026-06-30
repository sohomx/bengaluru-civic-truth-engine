from __future__ import annotations

import re
from typing import Any


EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_RE = re.compile(r"(?<!\d)(?:\+?91[-\s]?)?[6-9]\d{9}(?!\d)")
ACCOUNT_RE = re.compile(
    r"\b(?:rr\s*(?:number|no\.?)?|account\s*(?:number|no\.?)?)\s*[:#-]?\s*[A-Z0-9/-]*\d[A-Z0-9/-]{5,}\b",
    re.IGNORECASE,
)


def redact_pii(value: Any) -> str:
    text = "" if value is None else str(value)
    text = ACCOUNT_RE.sub("[REDACTED_ACCOUNT]", text)
    text = EMAIL_RE.sub("[REDACTED_EMAIL]", text)
    text = PHONE_RE.sub("[REDACTED_PHONE]", text)
    return text


def contains_public_pii(value: Any) -> bool:
    text = "" if value is None else str(value)
    return bool(EMAIL_RE.search(text) or PHONE_RE.search(text) or ACCOUNT_RE.search(text))


def redact_record(value: dict[str, Any], keys: set[str] | None = None) -> dict[str, Any]:
    redact_keys = {key.lower() for key in keys} if keys else set()
    result: dict[str, Any] = {}
    for key, item in value.items():
        if isinstance(item, str) and (not redact_keys or key.lower() in redact_keys):
            result[key] = redact_pii(item)
        else:
            result[key] = item
    return result
