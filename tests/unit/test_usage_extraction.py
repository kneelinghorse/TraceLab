"""METER-0: reading a DeepSearch run's accounting out of execution_metadata.

The sample mirrors the shape observed on production mission TRACE-SHARE-58
(2026-09-22), trimmed to the keys the recorder reads.
"""

from __future__ import annotations

import pytest

from app.services.usage_recorder import extract_run_usage

pytestmark = pytest.mark.unit

PRODUCTION_SHAPE = {
    "total_tokens": 2219061,
    "duration_seconds": 302.47,
    "quality_record": {"hit_max_steps": False, "terminating_step": 25},
    "runtime_identity": {"model": "deepseek-flash", "llm_backend": "deepseek", "build_hash": "6adab231"},
    "synthesis_telemetry": {
        "model_id": "deepseek-flash",
        "step_count": 25,
        "token_usage": {"input": 2127653, "total": 2159933, "output": 32280},
        "effective_model": {"provider": "deepseek", "requested_model": "deepseek-flash"},
        "tool_call_summary": {"by_tool": {"web_search": 44}},
        "recovery": {
            "attempt_accounting": {
                "steps_used": 25,
                "token_usage": {"input": 2182916, "total": 2219061, "output": 36145},
                "token_usage_complete": True,
                "model_accounting": {"requests": 27, "usage_complete": True},
            }
        },
    },
}


def test_reads_the_attempt_level_accounting_not_the_synthesis_subtotal():
    usage = extract_run_usage(PRODUCTION_SHAPE)
    assert usage.total_tokens == 2219061
    assert usage.input_tokens == 2182916
    assert usage.output_tokens == 36145
    assert usage.requests == 27
    assert usage.steps == 25
    assert usage.tool_calls == 44
    assert usage.duration_seconds == 302.47
    assert usage.model == "deepseek-flash"
    assert usage.provider == "deepseek"
    assert usage.usage_complete is True
    assert usage.details == {
        "tool_calls_by_tool": {"web_search": 44},
        "hit_max_steps": False,
        "worker_build_hash": "6adab231",
    }


def test_older_runs_with_only_the_contract_fields_still_record_what_exists():
    usage = extract_run_usage({"loops_executed": 3, "duration_seconds": 12.5, "model_used": "gpt-4o-mini"})
    assert usage.total_tokens is None
    assert usage.input_tokens is None
    assert usage.duration_seconds == 12.5
    assert usage.model == "gpt-4o-mini"
    assert usage.usage_complete is None
    assert usage.details is None


def test_missing_or_malformed_metadata_yields_an_empty_record():
    for value in (None, {}, [], "text", {"total_tokens": "not-a-number", "synthesis_telemetry": "x"}):
        usage = extract_run_usage(value)
        assert usage.total_tokens is None and usage.model is None and usage.requests is None


def test_falls_back_to_synthesis_token_usage_when_attempt_accounting_is_absent():
    usage = extract_run_usage({"synthesis_telemetry": {"token_usage": {"input": 10, "output": 5, "total": 15}}})
    assert (usage.input_tokens, usage.output_tokens, usage.total_tokens) == (10, 5, 15)
