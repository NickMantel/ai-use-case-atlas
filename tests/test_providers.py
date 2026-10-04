"""Provider plumbing, checked with fake SDK clients (no network)."""
import json
from types import SimpleNamespace

from app.config import get_framework
from app.models import UseCase
from app.providers.anthropic_provider import AnthropicProvider
from app.providers.base import inline_refs, parse_json_text
from app.providers.openai_compatible import OpenAICompatibleProvider
from app.services import ai
from app.services.ai_schemas import ExtractionResult, ScoreSuggestion, SizingSuggestion, StarterSQL, StoryDraft, canvas_model

GOOD_SCORE = {
    lens: {"level": "H", "rationale": "r", "question_answers": ["a", "b"], "confidence": "medium", "missing_information": []}
    for lens in ("desirability", "feasibility", "viability")
} | {"summary": "ok"}


def _no_refs(node):
    if isinstance(node, dict):
        assert "$ref" not in node and "$defs" not in node
        for v in node.values():
            _no_refs(v)
    elif isinstance(node, list):
        for v in node:
            _no_refs(v)


def test_schemas_flatten():
    for model in (ExtractionResult, StoryDraft, ScoreSuggestion, SizingSuggestion, StarterSQL, canvas_model(["a", "b"])):
        _no_refs(inline_refs(model.model_json_schema()))


def test_parse_json_text():
    assert parse_json_text('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json_text('Here you go: {"a": {"b": 2}} done') == {"a": {"b": 2}}


class FakeAnthropicMessages:
    def __init__(self, payloads):
        self.payloads, self.calls = list(payloads), []

    def create(self, **kw):
        self.calls.append(kw)
        block = SimpleNamespace(type="tool_use", name="submit_result", input=self.payloads.pop(0))
        return SimpleNamespace(content=[block], stop_reason="tool_use")


def _anthropic(payloads):
    p = AnthropicProvider.__new__(AnthropicProvider)
    p.model, p.max_tokens, p.timeout_s, p.name = "test-model", 1000, 10, "anthropic"
    p.client = SimpleNamespace(messages=FakeAnthropicMessages(payloads))
    return p


def test_anthropic_forced_tool_and_validation_retry():
    fw = get_framework()
    uc = UseCase(ref="UC-900", title="T", role="planner", need="n", outcome="o", workshop_answers={}, scores={}, catalog_evidence={})
    bad = {"desirability": {"level": "Very high"}}  # fails validation, triggers one retry
    p = _anthropic([bad, GOOD_SCORE])
    out = ai.suggest_scores(p, fw, uc)
    assert out["lenses"]["feasibility"]["level"] == "H"
    first, second = p.client.messages.calls
    assert first["tool_choice"] == {"type": "tool", "name": "submit_result"}
    assert first["model"] == "test-model" and "Desirability" in first["messages"][0]["content"]
    assert "failed validation" in second["messages"][0]["content"]


def test_openai_compatible_tool_call():
    p = OpenAICompatibleProvider.__new__(OpenAICompatibleProvider)
    p.model, p.max_tokens, p.timeout_s = "databricks-endpoint", 1000, 10
    calls = []

    def create(**kw):
        calls.append(kw)
        call = SimpleNamespace(function=SimpleNamespace(name="submit_result", arguments=json.dumps({"sql": "SELECT 1", "explanation": "e"})))
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(tool_calls=[call], content=None))])

    p.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    assert p.generate("sql", "sys", "prompt", StarterSQL.model_json_schema())["sql"] == "SELECT 1"
    assert calls[0]["tool_choice"]["function"]["name"] == "submit_result"
