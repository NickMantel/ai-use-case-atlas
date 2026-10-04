from __future__ import annotations

from typing import Any

from .base import LLMError, LLMProvider, inline_refs

TOOL_NAME = "submit_result"


class AnthropicProvider(LLMProvider):
    """Claude via the Anthropic API (ANTHROPIC_API_KEY) or, with `vertex=True`,
    Claude on Google Vertex AI (application default credentials)."""

    name = "anthropic"

    def __init__(self, *args, vertex_project: str = "", vertex_region: str = "", vertex: bool = False, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover
            raise LLMError("pip install anthropic") from exc
        if vertex:
            self.name = "vertex"
            self.client = anthropic.AnthropicVertex(project_id=vertex_project, region=vertex_region, timeout=self.timeout_s)
        else:
            self.client = anthropic.Anthropic(timeout=self.timeout_s)
        if not self.model:
            raise LLMError("LLM_MODEL must be set for the anthropic/vertex provider")

    def generate(self, task: str, system: str, prompt: str, schema: dict[str, Any], hints: dict[str, Any] | None = None) -> dict[str, Any]:
        tool = {
            "name": TOOL_NAME,
            "description": f"Submit the structured result for task '{task}'.",
            "input_schema": inline_refs(schema),
        }
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            tools=[tool],
            tool_choice={"type": "tool", "name": TOOL_NAME},
            messages=[{"role": "user", "content": prompt}],
        )
        for block in resp.content:
            if getattr(block, "type", None) == "tool_use" and block.name == TOOL_NAME:
                return dict(block.input)
        raise LLMError(f"No structured result returned (stop_reason={resp.stop_reason})")
