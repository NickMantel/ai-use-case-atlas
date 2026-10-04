from __future__ import annotations

import copy
import json
from abc import ABC, abstractmethod
from typing import Any


class LLMError(RuntimeError):
    pass


class LLMProvider(ABC):
    """One method: return a JSON object that matches `schema`.

    Every task in the app is structured output. Providers enforce it with
    forced tool calls where available, then the caller validates the result
    with pydantic, so a malformed answer fails loudly instead of corrupting
    a use case."""

    name: str = "base"
    is_stub: bool = False

    def __init__(self, model: str = "", max_tokens: int = 4096, timeout_s: float = 120):
        self.model = model
        self.max_tokens = max_tokens
        self.timeout_s = timeout_s

    @abstractmethod
    def generate(self, task: str, system: str, prompt: str, schema: dict[str, Any], hints: dict[str, Any] | None = None) -> dict[str, Any]:
        ...

    def describe(self) -> str:
        return f"{self.name} ({self.model or 'no model set'})"


def inline_refs(schema: dict[str, Any]) -> dict[str, Any]:
    """Resolve local $ref/$defs so every provider sees a flat JSON schema."""
    schema = copy.deepcopy(schema)
    defs = schema.pop("$defs", {})

    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                name = node["$ref"].split("/")[-1]
                resolved = walk(copy.deepcopy(defs[name]))
                extra = {k: v for k, v in node.items() if k != "$ref"}
                return {**resolved, **extra}
            return {k: walk(v) for k, v in node.items()}
        if isinstance(node, list):
            return [walk(v) for v in node]
        return node

    return walk(schema)


def parse_json_text(text: str) -> dict[str, Any]:
    """Fallback for providers that return JSON as text rather than a tool call."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        text = text.rsplit("```", 1)[0]
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise LLMError("Model did not return JSON")
    return json.loads(text[start : end + 1])
