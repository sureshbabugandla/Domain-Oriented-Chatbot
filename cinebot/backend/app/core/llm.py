"""LLM provider abstraction.

A tiny interface over OpenAI and Ollama so the rest of the app doesn't
need to know which backend is active. Every call is:
  * wrapped in tenacity retry with exponential backoff
  * bounded by ``settings.llm_timeout_seconds``
  * protected by a breaker-style fallback — if the LLM fails N times,
    callers can fall back to a template response

Both ``complete`` (sync) and ``stream`` (async generator) are supported.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import settings
from app.core.logging import get_logger

if TYPE_CHECKING:
    import httpx
    from openai import AsyncOpenAI

log = get_logger("llm")


@dataclass
class ChatMessage:
    role: str     # "system" | "user" | "assistant"
    content: str


class LLMProvider(ABC):
    """Interface every backend implements."""

    @abstractmethod
    async def complete(self, messages: Sequence[ChatMessage]) -> str: ...

    @abstractmethod
    async def stream(
        self, messages: Sequence[ChatMessage]
    ) -> AsyncIterator[str]: ...


# ── OpenAI ───────────────────────────────────────────────
class OpenAIProvider(LLMProvider):
    def __init__(self) -> None:
        from openai import AsyncOpenAI
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required when LLM_PROVIDER=openai")
        self._client: AsyncOpenAI = AsyncOpenAI(
            api_key=settings.openai_api_key,
            timeout=settings.llm_timeout_seconds,
        )

    async def complete(self, messages: Sequence[ChatMessage]) -> str:
        resp = await self._client.chat.completions.create(
            model=settings.openai_model,
            messages=[{"role": m.role, "content": m.content} for m in messages],
            temperature=settings.openai_temperature,
            stream=False,
        )
        return resp.choices[0].message.content or ""

    async def stream(self, messages: Sequence[ChatMessage]) -> AsyncIterator[str]:
        stream = await self._client.chat.completions.create(
            model=settings.openai_model,
            messages=[{"role": m.role, "content": m.content} for m in messages],
            temperature=settings.openai_temperature,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta


# ── Ollama ───────────────────────────────────────────────
class OllamaProvider(LLMProvider):
    def __init__(self) -> None:
        import httpx
        self._http: httpx.AsyncClient = httpx.AsyncClient(
            base_url=settings.ollama_base_url,
            timeout=settings.llm_timeout_seconds,
        )

    async def complete(self, messages: Sequence[ChatMessage]) -> str:
        resp = await self._http.post(
            "/api/chat",
            json={
                "model": settings.ollama_model,
                "messages": [
                    {"role": m.role, "content": m.content} for m in messages
                ],
                "options": {"temperature": settings.ollama_temperature},
                "stream": False,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return str(data.get("message", {}).get("content", ""))

    async def stream(self, messages: Sequence[ChatMessage]) -> AsyncIterator[str]:
        import json as _json
        async with self._http.stream(
            "POST",
            "/api/chat",
            json={
                "model": settings.ollama_model,
                "messages": [
                    {"role": m.role, "content": m.content} for m in messages
                ],
                "options": {"temperature": settings.ollama_temperature},
                "stream": True,
            },
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.strip():
                    continue
                try:
                    chunk = _json.loads(line)
                except ValueError:
                    continue
                delta = chunk.get("message", {}).get("content", "")
                if delta:
                    yield delta
                if chunk.get("done"):
                    return


# ── Retry wrapper ────────────────────────────────────────
class RetryingProvider(LLMProvider):
    """Wraps any provider with retry + logging. ``stream`` is not retried —
    restarting a token stream mid-flight would produce duplicates."""

    def __init__(self, inner: LLMProvider) -> None:
        self._inner = inner

    async def complete(self, messages: Sequence[ChatMessage]) -> str:
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(settings.llm_max_retries + 1),
            wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
            retry=retry_if_exception_type(Exception),
            reraise=True,
        ):
            with attempt:
                try:
                    return await self._inner.complete(messages)
                except Exception as e:
                    log.warning(
                        "llm_retry",
                        attempt=attempt.retry_state.attempt_number,
                        error=str(e)[:200],
                    )
                    raise
        raise RuntimeError("unreachable")

    async def stream(self, messages: Sequence[ChatMessage]) -> AsyncIterator[str]:
        async for token in self._inner.stream(messages):
            yield token


# ── Factory ──────────────────────────────────────────────
_provider: LLMProvider | None = None


def get_llm() -> LLMProvider:
    """Cached, provider-selected via LLM_PROVIDER env."""
    global _provider
    if _provider is not None:
        return _provider
    log.info("llm_init", provider=settings.llm_provider)
    if settings.llm_provider == "openai":
        _provider = RetryingProvider(OpenAIProvider())
    elif settings.llm_provider == "ollama":
        _provider = RetryingProvider(OllamaProvider())
    else:
        raise ValueError(f"unknown LLM_PROVIDER={settings.llm_provider!r}")
    return _provider
