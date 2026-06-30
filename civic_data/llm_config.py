from __future__ import annotations

import os
from dataclasses import dataclass


DEFAULT_LLM_MODEL = "gpt-5.4-mini"
DEFAULT_ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
DEFAULT_PROVIDER = "openai"
DETERMINISTIC_PROMPT_VERSION = "packet-explainer-deterministic-v1"
LLM_PROMPT_VERSION = "packet-explainer-v1"


@dataclass(frozen=True)
class PacketRagConfig:
    generation_mode: str
    provider: str
    llm_model: str
    embedding_model: str
    prompt_version: str
    api_key: str
    retrieval_mode: str = "packet_lexical"

    @classmethod
    def from_env(cls, mode: str | None = None) -> "PacketRagConfig":
        generation_mode = (mode or os.environ.get("CIVIC_LLM_MODE") or "deterministic").strip().lower()
        if generation_mode not in {"deterministic", "llm"}:
            raise ValueError("CIVIC_LLM_MODE must be deterministic or llm")
        provider = (os.environ.get("CIVIC_LLM_PROVIDER") or DEFAULT_PROVIDER).strip().lower()
        if provider not in {"openai", "anthropic"}:
            raise ValueError("CIVIC_LLM_PROVIDER must be openai or anthropic")
        llm_model = _llm_model(provider)
        embedding_model = os.environ.get("CIVIC_EMBEDDING_MODEL") or DEFAULT_EMBEDDING_MODEL
        prompt_version = LLM_PROMPT_VERSION if generation_mode == "llm" else DETERMINISTIC_PROMPT_VERSION
        return cls(
            generation_mode=generation_mode,
            provider=provider if generation_mode != "deterministic" else "none",
            llm_model=llm_model if generation_mode != "deterministic" else "",
            embedding_model=embedding_model if generation_mode != "deterministic" else "",
            prompt_version=prompt_version,
            api_key=_api_key(provider),
            retrieval_mode=os.environ.get("CIVIC_RAG_RETRIEVAL") or "packet_lexical",
        )

    def require_llm_key(self) -> None:
        if self.generation_mode == "llm" and self.provider == "openai" and not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is required when CIVIC_LLM_MODE=llm")
        if self.generation_mode == "llm" and self.provider == "anthropic" and not self.api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is required when CIVIC_LLM_PROVIDER=anthropic")


def _api_key(provider: str) -> str:
    if provider == "anthropic":
        return os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("CIVIC_ANTHROPIC_API_KEY") or ""
    return os.environ.get("OPENAI_API_KEY") or os.environ.get("CIVIC_OPENAI_API_KEY") or ""


def _llm_model(provider: str) -> str:
    if provider == "anthropic":
        return os.environ.get("ANTHROPIC_MODEL") or os.environ.get("CIVIC_LLM_MODEL") or DEFAULT_ANTHROPIC_MODEL
    return os.environ.get("CIVIC_LLM_MODEL") or DEFAULT_LLM_MODEL
