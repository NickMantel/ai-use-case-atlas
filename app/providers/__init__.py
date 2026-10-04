from __future__ import annotations

from functools import lru_cache

from ..config import get_settings
from .base import LLMError, LLMProvider
from .stub import StubProvider


def build_provider(name: str | None = None) -> LLMProvider:
    s = get_settings()
    name = (name or s.llm_provider).lower()
    common = {"model": s.llm_model, "max_tokens": s.llm_max_tokens, "timeout_s": s.llm_timeout_s}
    if name == "stub":
        return StubProvider(**common)
    if name == "anthropic":
        from .anthropic_provider import AnthropicProvider

        return AnthropicProvider(**common)
    if name == "vertex":
        from .anthropic_provider import AnthropicProvider

        return AnthropicProvider(**common, vertex=True, vertex_project=s.vertex_project, vertex_region=s.vertex_region)
    if name == "databricks":
        from .openai_compatible import OpenAICompatibleProvider

        return OpenAICompatibleProvider(**common, databricks=True)
    if name in ("openai_compatible", "azure_openai"):
        from .openai_compatible import OpenAICompatibleProvider

        return OpenAICompatibleProvider(**common, base_url=s.openai_base_url, api_key=s.openai_api_key)
    raise LLMError(f"Unknown LLM_PROVIDER '{name}'")


@lru_cache
def get_provider() -> LLMProvider:
    return build_provider()


__all__ = ["LLMError", "LLMProvider", "build_provider", "get_provider"]
