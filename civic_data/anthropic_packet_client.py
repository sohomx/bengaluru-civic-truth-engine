from __future__ import annotations

import json
import re
from typing import Any, Callable
from urllib.error import HTTPError
from urllib.request import Request, urlopen


MESSAGES_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"


class AnthropicMessagesPacketClient:
    def __init__(self, transport: Callable[[Request, int], dict[str, object]] | None = None) -> None:
        self._transport = transport or _default_transport

    def create_packet_explanation(self, *, prompt: dict[str, object], schema: dict[str, object], config: object) -> dict[str, object]:
        api_key = str(getattr(config, "api_key", ""))
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is required for Anthropic packet explanation")
        body = {
            "model": str(getattr(config, "llm_model", "claude-haiku-4-5-20251001")),
            "max_tokens": 900,
            "system": str(prompt["system"]),
            "messages": [
                {
                    "role": "user",
                    "content": (
                        "Return only valid JSON matching this schema. Do not wrap it in markdown.\n\n"
                        f"SCHEMA:\n{json.dumps(schema, ensure_ascii=True, sort_keys=True)}\n\n"
                        f"PACKET_INPUT:\n{json.dumps(prompt['user'], ensure_ascii=True, sort_keys=True)}"
                    ),
                }
            ],
        }
        request = Request(
            MESSAGES_URL,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "x-api-key": api_key,
                "anthropic-version": ANTHROPIC_VERSION,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        payload = self._transport(request, 30)
        text = _response_text(payload)
        try:
            result = json.loads(_strip_json_fence(text))
        except json.JSONDecodeError as exc:
            raise RuntimeError("Anthropic Messages API returned non-JSON packet explanation") from exc
        if not isinstance(result, dict):
            raise RuntimeError("Anthropic Messages API returned a non-object packet explanation")
        result["_llm_response_id"] = payload.get("id")
        result["_usage"] = payload.get("usage") or {}
        return result


def _default_transport(request: Request, timeout: int) -> dict[str, object]:
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Anthropic Messages API failed with {exc.code}: {_safe_error_detail(detail)}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("Anthropic Messages API returned a non-object response")
    return payload


def _response_text(payload: dict[str, object]) -> str:
    content = payload.get("content")
    if not isinstance(content, list):
        raise RuntimeError("Anthropic Messages API response missing content array")
    parts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "text" and isinstance(item.get("text"), str):
            parts.append(str(item["text"]))
    text = "\n".join(parts).strip()
    if not text:
        raise RuntimeError("Anthropic Messages API response did not contain text content")
    return text


def _strip_json_fence(text: str) -> str:
    stripped = text.strip()
    match = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", stripped, flags=re.DOTALL)
    return match.group(1).strip() if match else stripped


def _safe_error_detail(detail: str) -> str:
    return re.sub(r"sk-ant-[A-Za-z0-9_-]+", "[redacted]", detail)[:1000]
