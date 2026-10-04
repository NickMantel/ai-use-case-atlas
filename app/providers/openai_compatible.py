from __future__ import annotations

import json
from typing import Any

from .base import LLMError, LLMProvider, inline_refs, parse_json_text

TOOL_NAME = "submit_result"


class OpenAICompatibleProvider(LLMProvider):
    """Any OpenAI-style chat completions endpoint.

    Covers Databricks Model Serving (OPENAI_BASE_URL=https://<workspace>/serving-endpoints,
    OPENAI_API_KEY=<PAT or OAuth token>, LLM_MODEL=<endpoint name>), Azure OpenAI's
    v1 endpoint, and internal gateways such as LiteLLM proxy."""

    name = "openai_compatible"

    def __init__(self, *args, base_url: str = "", api_key: str = "", databricks: bool = False, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.model:
            raise LLMError("LLM_MODEL must be set for the openai_compatible/databricks provider")
        if databricks:
            # Databricks Model Serving with SDK unified auth (PAT, OAuth, or the
            # Databricks App's own service principal). No token handling in app code.
            try:
                from databricks.sdk import WorkspaceClient
            except ImportError as exc:  # pragma: no cover
                raise LLMError("pip install databricks-sdk openai") from exc
            self.name = "databricks"
            self.client = WorkspaceClient().serving_endpoints.get_open_ai_client()
            return
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover
            raise LLMError("pip install openai") from exc
        self.client = OpenAI(base_url=base_url or None, api_key=api_key or None, timeout=self.timeout_s)

    def generate(self, task: str, system: str, prompt: str, schema: dict[str, Any], hints: dict[str, Any] | None = None) -> dict[str, Any]:
        tool = {
            "type": "function",
            "function": {
                "name": TOOL_NAME,
                "description": f"Submit the structured result for task '{task}'.",
                "parameters": inline_refs(schema),
            },
        }
        resp = self.client.chat.completions.create(
            model=self.model,
            max_tokens=self.max_tokens,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            tools=[tool],
            tool_choice={"type": "function", "function": {"name": TOOL_NAME}},
        )
        msg = resp.choices[0].message
        for call in msg.tool_calls or []:
            if call.function.name == TOOL_NAME:
                return json.loads(call.function.arguments)
        if msg.content:
            return parse_json_text(msg.content)
        raise LLMError("No structured result returned")
