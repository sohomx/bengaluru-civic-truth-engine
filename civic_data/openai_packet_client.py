from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen


RESPONSES_URL = "https://api.openai.com/v1/responses"


class OpenAIResponsesPacketClient:
    def create_packet_explanation(self, *, prompt: dict[str, object], schema: dict[str, object], config: object) -> dict[str, object]:
        api_key = str(getattr(config, "api_key", ""))
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is required for OpenAI packet explanation")
        body = {
            "model": getattr(config, "llm_model", "gpt-5.4-mini"),
            "input": [
                {"role": "system", "content": str(prompt["system"])},
                {"role": "user", "content": json.dumps(prompt["user"], ensure_ascii=True, sort_keys=True)},
            ],
            "reasoning": {"effort": "low"},
            "store": False,
            "text": {
                "verbosity": "low",
                "format": {
                    "type": "json_schema",
                    "name": "civic_packet_explanation",
                    "strict": True,
                    "schema": schema,
                },
            },
        }
        request = Request(
            RESPONSES_URL,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"OpenAI Responses API failed with {exc.code}: {detail}") from exc
        text = _response_text(payload)
        try:
            result = json.loads(text)
        except json.JSONDecodeError as exc:
            raise RuntimeError("OpenAI Responses API returned non-JSON packet explanation") from exc
        result["_openai_response_id"] = payload.get("id")
        result["_usage"] = payload.get("usage") or {}
        return result


def _response_text(payload: dict[str, Any]) -> str:
    value = payload.get("output_text")
    if isinstance(value, str) and value.strip():
        return value
    parts: list[str] = []
    for item in payload.get("output", []) if isinstance(payload.get("output"), list) else []:
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []) if isinstance(item.get("content"), list) else []:
            if isinstance(content, dict) and isinstance(content.get("text"), str):
                parts.append(content["text"])
    return "\n".join(parts)
