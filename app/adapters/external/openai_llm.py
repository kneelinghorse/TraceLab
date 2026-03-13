# ABOUTME: Adapter bridging OpenAI chat completions to the LLMPort protocol.
# ABOUTME: Provides a clean interface for text generation without coupling to OpenAI SDK.

from __future__ import annotations

from app.core.config import settings

try:
    from openai import OpenAI
except ModuleNotFoundError:
    OpenAI = None  # type: ignore


class OpenAILLMAdapter:
    """Adapter bridging OpenAI chat completions to LLMPort protocol."""

    def __init__(self, client: OpenAI | None = None, default_model: str | None = None):
        if client is not None:
            self._client = client
        elif OpenAI is not None and settings.openai_api_key:
            self._client = OpenAI(api_key=settings.openai_api_key)
        else:
            raise RuntimeError("OpenAI SDK required and OPENAI_API_KEY must be set")

        self._default_model = default_model or getattr(settings, "openai_model", "gpt-4o-mini")

    def complete(
        self,
        *,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 2000,
    ) -> str:
        response = self._client.chat.completions.create(
            model=model or self._default_model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content or ""
