"""Provider seam for the Librarian (LIB-1).

Decision #518: the model behind each Librarian stage is configuration, never a
constant, and the transport must not bake in assumptions that fail on one
provider. This module is the Librarian's only contact with the OpenAI SDK, so a
different transport (the Responses API, for instance) is a change here and
nowhere else.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from app.core.config import settings

try:
    from openai import APIError, OpenAI, RateLimitError
except ModuleNotFoundError as exc:  # pragma: no cover - exercised only without the SDK
    OpenAI = None  # type: ignore[assignment,misc]
    APIError = RateLimitError = Exception  # type: ignore[misc,assignment]
    _openai_import_error: ModuleNotFoundError | None = exc
else:
    _openai_import_error = None

logger = logging.getLogger(__name__)

__all__ = [
    "APIError",
    "ChatCompletionsModel",
    "LibrarianUnavailable",
    "ModelReply",
    "ModelToolCall",
    "RateLimitError",
    "get_librarian_model",
]


class LibrarianUnavailable(RuntimeError):
    """The Librarian has no usable model configuration."""


@dataclass
class ModelToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ModelReply:
    content: str | None
    tool_calls: list[ModelToolCall] = field(default_factory=list)
    usage: dict[str, int] | None = None


def _uses_completion_tokens(model_name: str) -> bool:
    # The GPT-5 family rejects ``max_tokens``; OpenAI-compatible providers such as
    # DeepSeek reject ``max_completion_tokens``. Same split the RAG and synthesis
    # services apply, widened to the whole family so a dated alias is not left out.
    return model_name.lower().startswith("gpt-5")


def _extract_usage(response: Any) -> dict[str, int] | None:
    usage = getattr(response, "usage", None)
    if usage is None:
        return None
    if isinstance(usage, dict):
        prompt = usage.get("prompt_tokens", 0) or 0
        completion = usage.get("completion_tokens", 0) or 0
        total = usage.get("total_tokens", prompt + completion) or (prompt + completion)
    else:
        prompt = getattr(usage, "prompt_tokens", 0) or 0
        completion = getattr(usage, "completion_tokens", 0) or 0
        total = getattr(usage, "total_tokens", prompt + completion) or (prompt + completion)
    return {
        "prompt_tokens": int(prompt),
        "completion_tokens": int(completion),
        "total_tokens": int(total),
    }


def _parse_arguments(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _parse_reply(response: Any) -> ModelReply:
    choices = getattr(response, "choices", None) or []
    if not choices:
        return ModelReply(content=None, usage=_extract_usage(response))
    message = getattr(choices[0], "message", None)
    content = getattr(message, "content", None)
    tool_calls: list[ModelToolCall] = []
    for call in getattr(message, "tool_calls", None) or []:
        function = getattr(call, "function", None)
        name = getattr(function, "name", None)
        if not name:
            continue
        tool_calls.append(
            ModelToolCall(
                id=str(getattr(call, "id", "") or f"call_{len(tool_calls)}"),
                name=str(name),
                arguments=_parse_arguments(getattr(function, "arguments", None)),
            )
        )
    return ModelReply(
        content=content if isinstance(content, str) else None,
        tool_calls=tool_calls,
        usage=_extract_usage(response),
    )


class ChatCompletionsModel:
    """Chat Completions transport.

    ``reasoning_effort`` is deliberately never sent: combined with function tools it
    returns HTTP 400 on at least one provider (DeepSearch sprint 93, m09), and the
    Librarian's replies are short enough not to need it.
    """

    def __init__(self, client: Any, model_name: str) -> None:
        self.client = client
        self.model_name = model_name

    def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        json_mode: bool = False,
        max_tokens: int = 1500,
    ) -> ModelReply:
        token_key = "max_completion_tokens" if _uses_completion_tokens(self.model_name) else "max_tokens"
        request: dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            token_key: max_tokens,
        }
        if tools:
            request["tools"] = tools
            request["tool_choice"] = "auto"
        if json_mode:
            request["response_format"] = {"type": "json_object"}
        response = self.client.chat.completions.create(**request)
        return _parse_reply(response)


def get_librarian_model() -> ChatCompletionsModel:
    """Build the configured model, or raise ``LibrarianUnavailable`` (mapped to 503)."""
    if OpenAI is None:
        raise LibrarianUnavailable("The openai package is not installed.") from _openai_import_error
    api_key = settings.librarian_api_key or settings.openai_api_key
    if not api_key:
        raise LibrarianUnavailable(
            "No model API key is configured for the Librarian (LIBRARIAN_API_KEY or OPENAI_API_KEY)."
        )
    kwargs: dict[str, Any] = {"api_key": api_key}
    if settings.librarian_base_url:
        kwargs["base_url"] = settings.librarian_base_url
    return ChatCompletionsModel(OpenAI(**kwargs), settings.librarian_model or settings.openai_chat_model)
