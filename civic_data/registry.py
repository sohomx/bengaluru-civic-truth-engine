from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


URL_PATTERN = re.compile(r"https?://\S+")


def load_sources(path: Path) -> list[dict[str, Any]]:
    try:
        data = json.loads(path.read_text())
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"Registry file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"{path} must be JSON-compatible YAML until a YAML parser is added: {exc}"
        ) from exc
    if not isinstance(data, list):
        raise ValueError(f"{path} must contain a list of source objects")
    return data


def validate_registry(sources: list[dict[str, Any]], schema_path: Path) -> list[str]:
    schema = json.loads(schema_path.read_text())
    item_schema = schema["items"]
    required = item_schema["required"]
    properties = item_schema["properties"]
    errors: list[str] = []
    seen_ids: set[str] = set()

    for index, source in enumerate(sources):
        prefix = f"source[{index}]"
        if not isinstance(source, dict):
            errors.append(f"{prefix} must be an object")
            continue
        for field in required:
            if field not in source:
                errors.append(f"{prefix} missing required field {field}")
            elif source[field] in (None, ""):
                errors.append(f"{prefix}.{field} must not be empty")
        source_id = source.get("id")
        if isinstance(source_id, str):
            if source_id in seen_ids:
                errors.append(f"duplicate source id {source_id}")
            seen_ids.add(source_id)
        for field, field_schema in properties.items():
            if field not in source:
                continue
            if "enum" in field_schema and source[field] not in field_schema["enum"]:
                errors.append(
                    f"{prefix}.{field} has invalid value {source[field]!r}; "
                    f"expected one of {field_schema['enum']}"
                )
            expected_type = field_schema.get("type")
            if expected_type and not _matches_json_type(source[field], expected_type):
                errors.append(f"{prefix}.{field} must be {expected_type}")
    return errors


def registry_url_report(
    sources: list[dict[str, Any]], overview_path: Path
) -> dict[str, list[str]]:
    overview_urls = sorted(
        {url.rstrip(").,") for url in URL_PATTERN.findall(overview_path.read_text())}
    )
    url_to_sources: dict[str, list[str]] = {}
    for source in sources:
        urls = [source.get("url"), *source.get("aliases", [])]
        for url in urls:
            if isinstance(url, str):
                url_to_sources.setdefault(url, []).append(str(source.get("id", "")))

    missing = [url for url in overview_urls if url not in url_to_sources]
    duplicate_unaliased = []
    for url, ids in url_to_sources.items():
        unique_ids = sorted(set(ids))
        if len(unique_ids) > 1 and any(source.get("url") == url for source in sources):
            duplicate_unaliased.append(f"{url}: {', '.join(unique_ids)}")
    return {"missing": missing, "duplicate_unaliased": sorted(duplicate_unaliased)}


def registry_hash(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _matches_json_type(value: Any, expected_type: str | list[str]) -> bool:
    allowed = expected_type if isinstance(expected_type, list) else [expected_type]
    return any(_matches_single_json_type(value, item) for item in allowed)


def _matches_single_json_type(value: Any, expected_type: str) -> bool:
    if expected_type == "string":
        return isinstance(value, str)
    if expected_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected_type == "boolean":
        return isinstance(value, bool)
    if expected_type == "array":
        return isinstance(value, list)
    if expected_type == "object":
        return isinstance(value, dict)
    return True
