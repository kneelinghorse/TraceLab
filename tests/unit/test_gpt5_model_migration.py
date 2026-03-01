"""Unit tests for GPT-5 model migration behavior."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.cost_monitor import CostMonitor
from app.services.quality_assessment import QualityAssessor
from app.services.rag_service import RagService
from app.services.synthesis import SynthesisService


def _fake_completion_response(content: str = "ok") -> SimpleNamespace:
    message = SimpleNamespace(content=content)
    choice = SimpleNamespace(message=message)
    usage = SimpleNamespace(prompt_tokens=12, completion_tokens=48, total_tokens=60)
    return SimpleNamespace(choices=[choice], usage=usage)


class _FakeChatCompletions:
    def __init__(self, response: SimpleNamespace) -> None:
        self.response = response
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


class _FakeClient:
    def __init__(self, response: SimpleNamespace) -> None:
        self.chat = SimpleNamespace(completions=_FakeChatCompletions(response))


def test_cost_monitor_uses_gpt51_pricing() -> None:
    monitor = CostMonitor(retention_days=1)
    result = monitor.track_usage(
        model="gpt-5.1",
        prompt_tokens=1000,
        completion_tokens=500,
    )

    assert result["cost_usd"] == pytest.approx(0.00625)


def test_rag_service_gpt5_chat_request_includes_reasoning_effort() -> None:
    client = _FakeClient(_fake_completion_response("Answer text"))
    service = RagService.__new__(RagService)
    service.client = client
    service.primary_model = "gpt-5.1"

    answer, usage = RagService._generate_answer(
        service,
        messages=[{"role": "user", "content": "test"}],
        temperature=0.2,
        max_tokens=128,
        retry_max=1,
        model="gpt-5.1",
    )

    assert answer == "Answer text"
    assert usage and usage["total_tokens"] == 60
    request = client.chat.completions.calls[0]
    assert request["model"] == "gpt-5.1"
    assert request["reasoning_effort"] == "none"
    assert request["temperature"] == 0.2
    assert request["max_tokens"] == 128


def test_synthesis_service_gpt5_chat_request_includes_reasoning_effort() -> None:
    client = _FakeClient(_fake_completion_response("Synthesized text"))
    service = SynthesisService.__new__(SynthesisService)
    service.client = client
    service.model = "gpt-5.2"
    service.temperature = 0.35
    service.max_tokens = 256

    content, usage = SynthesisService._generate_completion(
        service,
        messages=[{"role": "user", "content": "summarize"}],
    )

    assert content == "Synthesized text"
    assert usage and usage["total_tokens"] == 60
    request = client.chat.completions.calls[0]
    assert request["model"] == "gpt-5.2"
    assert request["reasoning_effort"] == "none"
    assert request["temperature"] == 0.35
    assert request["max_tokens"] == 256


def test_quality_assessor_flags_cant_assist_refusal() -> None:
    assessor = QualityAssessor()
    result = assessor.assess(
        query="Summarize policies",
        answer="I can’t assist with that request.",
        citations=[],
        context_chunks=[],
    )

    assert result.escalate is True
    assert "refusal_detected" in result.hard_failures
