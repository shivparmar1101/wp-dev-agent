from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from backend.utils.logging import get_logger

from .provider import (
    AIAuthError,
    AIError,
    AIProvider,
    AIResult,
    AIMessage,
    AIRateLimitError,
    AIServerError,
    AITimeoutError,
    AIUnavailableError,
)

logger = get_logger(__name__)

# 429/5xx are usually transient overload (Google reports 503 "high demand").
_RETRYABLE_STATUS = {429, 500, 502, 503, 529}
_RETRY_ATTEMPTS = 3
_RETRY_BASE_DELAY_SECONDS = 1.5
# Keeps semantic ranking fast: full 3072-dim vectors would only slow cosine down.
_GEMINI_EMBEDDING_DIMS = 768


async def _send_with_retries(
    send: Callable[[], Awaitable[httpx.Response]],
    *,
    attempts: int = _RETRY_ATTEMPTS,
) -> httpx.Response:
    """Send a request, retrying transient provider failures with backoff.

    Without this a single upstream hiccup fails the whole chat request even
    though the same call usually succeeds a second later.
    """
    response = await send()
    for attempt in range(2, attempts + 1):
        if response.status_code not in _RETRYABLE_STATUS:
            break
        delay = _RETRY_BASE_DELAY_SECONDS * (2 ** (attempt - 2))
        logger.warning(
            "AI provider returned HTTP %s; retrying in %.1fs (attempt %s/%s)",
            response.status_code,
            delay,
            attempt,
            attempts,
        )
        await asyncio.sleep(delay)
        response = await send()
    return response


def _friendly_http_error(status: int, payload: Any) -> AIError:
    detail = ""
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            detail = str(error.get("message") or "")
        elif isinstance(error, str):
            detail = error
        else:
            detail = str(payload.get("message") or "")
    detail = detail[:500]

    if status in (401, 403):
        return AIAuthError("The AI provider rejected the configured credentials.", detail=detail)
    if status == 429:
        return AIRateLimitError("The AI provider rate limit was reached.", detail=detail)
    if status in (400, 404, 422):
        return AIError(
            "The AI provider rejected the request. Check AI_MODEL and AI_BASE_URL.",
            detail=detail,
        )
    if status >= 500:
        return AIServerError(
            "The AI provider returned a server error. Try again shortly.", detail=detail
        )
    return AIError("The AI provider returned an unexpected error.", detail=detail)


class OpenAIProvider(AIProvider):
    """OpenAI and any OpenAI-compatible endpoint (OpenRouter, Groq, Ollama...)."""

    name = "openai"

    @property
    def base_url(self) -> str:
        base = (self.settings.ai_base_url or "").strip() or "https://api.openai.com/v1"
        return base.rstrip("/")

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.settings.ai_api_key:
            headers["Authorization"] = f"Bearer {self.settings.ai_api_key}"
        return headers

    async def complete(
        self,
        messages: list[AIMessage],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AIResult:
        payload = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": self.settings.ai_temperature if temperature is None else temperature,
            "max_tokens": max_tokens or self.settings.ai_max_tokens,
        }
        data = await self._post(f"{self.base_url}/chat/completions", payload)
        try:
            choice = data["choices"][0]
            text = choice["message"]["content"] or ""
            usage = data.get("usage") or {}
            return AIResult(
                text=text,
                model=str(data.get("model") or self.model),
                provider=self.name,
                input_tokens=usage.get("prompt_tokens"),
                output_tokens=usage.get("completion_tokens"),
                finish_reason=choice.get("finish_reason"),
                raw=data,
            )
        except (KeyError, IndexError, TypeError) as exc:
            raise AIError("Unexpected response shape from the AI provider.", detail=str(exc)) from exc

    def supports_embeddings(self) -> bool:
        return True

    async def embed(self, texts: list[str]) -> list[list[float]] | None:
        if not texts:
            return []
        payload = {"model": self.settings.ai_embedding_model, "input": texts}
        try:
            data = await self._post(f"{self.base_url}/embeddings", payload)
        except AIError:
            return None
        try:
            items = sorted(data["data"], key=lambda item: item["index"])
            return [[float(x) for x in item["embedding"]] for item in items]
        except (KeyError, TypeError, ValueError):
            return None

    async def _post(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=self.settings.ai_timeout_seconds) as client:
                response = await _send_with_retries(
                    lambda: client.post(url, json=payload, headers=self._headers())
                )
        except httpx.TimeoutException as exc:
            raise AITimeoutError("The AI request timed out.") from exc
        except httpx.HTTPError as exc:
            raise AIError("Could not reach the AI provider.", detail=str(exc)) from exc

        try:
            data = response.json()
        except Exception:
            data = {"error": {"message": response.text[:300]}}
        if response.status_code >= 400:
            error = _friendly_http_error(response.status_code, data)
            logger.warning("AI provider error %s: %s", response.status_code, error.detail)
            raise error
        return data


class AnthropicProvider(AIProvider):
    name = "anthropic"

    @property
    def api_url(self) -> str:
        base = (self.settings.ai_base_url or "").strip() or "https://api.anthropic.com"
        return base.rstrip("/") + "/v1/messages"

    async def complete(
        self,
        messages: list[AIMessage],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AIResult:
        system_parts = [m.content for m in messages if m.role == "system"]
        chat = [m for m in messages if m.role in ("user", "assistant")]
        if not chat:
            raise AIError("No conversation content was provided to the model.")
        payload = {
            "model": self.model,
            "max_tokens": max_tokens or self.settings.ai_max_tokens,
            "temperature": self.settings.ai_temperature if temperature is None else temperature,
            "system": "\n\n".join(system_parts),
            "messages": [{"role": m.role, "content": m.content} for m in chat],
        }
        headers = {
            "x-api-key": self.settings.ai_api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=self.settings.ai_timeout_seconds) as client:
                response = await _send_with_retries(
                    lambda: client.post(self.api_url, json=payload, headers=headers)
                )
        except httpx.TimeoutException as exc:
            raise AITimeoutError("The AI request timed out.") from exc
        except httpx.HTTPError as exc:
            raise AIError("Could not reach the AI provider.", detail=str(exc)) from exc

        try:
            data = response.json()
        except Exception:
            data = {"error": {"message": response.text[:300]}}
        if response.status_code >= 400:
            raise _friendly_http_error(response.status_code, data)
        try:
            parts = data.get("content") or []
            text = "".join(p.get("text", "") for p in parts if p.get("type") == "text")
            usage = data.get("usage") or {}
            return AIResult(
                text=text,
                model=str(data.get("model") or self.model),
                provider=self.name,
                input_tokens=usage.get("input_tokens"),
                output_tokens=usage.get("output_tokens"),
                finish_reason=data.get("stop_reason"),
                raw=data,
            )
        except (KeyError, TypeError) as exc:
            raise AIError("Unexpected response shape from the AI provider.", detail=str(exc)) from exc


class GeminiProvider(AIProvider):
    name = "gemini"

    @property
    def api_url(self) -> str:
        base = (
            (self.settings.ai_base_url or "").strip()
            or "https://generativelanguage.googleapis.com/v1beta"
        )
        return base.rstrip("/") + f"/models/{self.model}:generateContent"

    async def complete(
        self,
        messages: list[AIMessage],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AIResult:
        system_parts = [m.content for m in messages if m.role == "system"]
        contents: list[dict[str, Any]] = []
        for message in messages:
            if message.role == "system":
                continue
            role = "model" if message.role == "assistant" else "user"
            contents.append({"role": role, "parts": [{"text": message.content}]})
        if not contents:
            raise AIError("No conversation content was provided to the model.")
        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": self.settings.ai_temperature if temperature is None else temperature,
                "maxOutputTokens": max_tokens or self.settings.ai_max_tokens,
            },
        }
        if system_parts:
            payload["systemInstruction"] = {"parts": [{"text": "\n\n".join(system_parts)}]}

        params = {"key": self.settings.ai_api_key}
        try:
            async with httpx.AsyncClient(timeout=self.settings.ai_timeout_seconds) as client:
                response = await _send_with_retries(
                    lambda: client.post(self.api_url, json=payload, params=params)
                )
        except httpx.TimeoutException as exc:
            raise AITimeoutError("The AI request timed out.") from exc
        except httpx.HTTPError as exc:
            raise AIError("Could not reach the AI provider.", detail=str(exc)) from exc

        try:
            data = response.json()
        except Exception:
            data = {"error": {"message": response.text[:300]}}
        if response.status_code >= 400:
            raise _friendly_http_error(response.status_code, data)
        try:
            candidates = data.get("candidates") or []
            parts = candidates[0]["content"]["parts"]
            text = "".join(p.get("text", "") for p in parts)
            usage = data.get("usageMetadata") or {}
            return AIResult(
                text=text,
                model=self.model,
                provider=self.name,
                input_tokens=usage.get("promptTokenCount"),
                output_tokens=usage.get("candidatesTokenCount"),
                finish_reason=candidates[0].get("finishReason"),
                raw=data,
            )
        except (KeyError, IndexError, TypeError) as exc:
            raise AIError("Unexpected response shape from the AI provider.", detail=str(exc)) from exc

    # -- embeddings --------------------------------------------------------
    def supports_embeddings(self) -> bool:
        return True

    @property
    def embedding_model_name(self) -> str:
        # `AI_EMBEDDING_MODEL` defaults to the OpenAI model name, which Gemini
        # rejects - fall back to the Gemini embedding model unless overridden.
        configured = (self.settings.ai_embedding_model or "").strip()
        if configured.startswith("gemini-embedding"):
            return configured
        return "gemini-embedding-001"

    async def embed(self, texts: list[str]) -> list[list[float]] | None:
        """Embed texts with `batchEmbedContents`.

        Any failure returns None so search silently keeps lexical ranking
        instead of breaking the request.
        """
        if not texts:
            return []
        model = self.embedding_model_name
        base = (
            (self.settings.ai_base_url or "").strip()
            or "https://generativelanguage.googleapis.com/v1beta"
        )
        url = f"{base.rstrip('/')}/models/{model}:batchEmbedContents"
        payload = {
            "requests": [
                {
                    "model": f"models/{model}",
                    "content": {"parts": [{"text": text}]},
                    "outputDimensionality": _GEMINI_EMBEDDING_DIMS,
                }
                for text in texts
            ]
        }
        try:
            async with httpx.AsyncClient(timeout=self.settings.ai_timeout_seconds) as client:
                response = await _send_with_retries(
                    lambda: client.post(
                        url, json=payload, params={"key": self.settings.ai_api_key}
                    )
                )
        except (httpx.TimeoutException, httpx.HTTPError) as exc:
            logger.warning("Gemini embeddings request failed: %s", exc)
            return None
        if response.status_code >= 400:
            logger.warning(
                "Gemini embeddings returned HTTP %s: %s",
                response.status_code,
                response.text[:200],
            )
            return None
        try:
            items = response.json().get("embeddings") or []
            vectors = [[float(value) for value in item["values"]] for item in items]
        except (AttributeError, KeyError, TypeError, ValueError):
            return None
        if len(vectors) != len(texts) or not vectors:
            return None
        return vectors


class MockProvider(AIProvider):
    """Deterministic offline provider used for tests and local development.

    It never invents repository content: it echoes back the files that were
    actually placed in the prompt context.
    """

    name = "mock"
    requires_key = False

    _FILE_RE = re.compile(r"^### FILE: (.+?) \[lines (\d+)-(\d+)\]", re.MULTILINE)

    async def complete(
        self,
        messages: list[AIMessage],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AIResult:
        user_text = "\n".join(m.content for m in messages if m.role == "user")
        question = ""
        for message in reversed(messages):
            if message.role == "user":
                match = re.search(r"## Question\n(.+?)\n", message.content, re.DOTALL)
                question = (match.group(1).strip() if match else message.content.strip())[:400]
                break

        files: list[dict[str, Any]] = []
        seen: set[str] = set()
        for match in self._FILE_RE.finditer(user_text):
            path, start, end = match.group(1), int(match.group(2)), int(match.group(3))
            if path in seen:
                continue
            seen.add(path)
            snippet_match = re.search(
                re.escape(f"### FILE: {path} [lines {start}-{end}]\n") + r"```[a-z]*\n(.*?)```",
                user_text,
                re.DOTALL,
            )
            snippet = (snippet_match.group(1).strip() if snippet_match else "")[:400]
            files.append(
                {
                    "file_path": path,
                    "start_line": start,
                    "end_line": end,
                    "snippet": snippet,
                }
            )
            if len(files) >= 4:
                break

        payload = {
            "issue": question or "Repository question received.",
            "relevant_files": files,
            "cause": (
                "Mock analysis: no AI model was called. This response only reflects "
                "the files retrieved from the repository index."
            ),
            "suggested_solution": (
                "Configure AI_PROVIDER and AI_API_KEY to receive a real AI analysis "
                "of this repository."
            ),
            "solution_language": None,
            "confidence": "Unknown",
            "explanation": (
                "The offline mock provider echoes the retrieved context. Search and "
                "indexing still ran against the real repository."
            ),
        }
        return AIResult(
            text=json.dumps(payload),
            model="mock",
            provider=self.name,
            input_tokens=None,
            output_tokens=None,
            finish_reason="stop",
        )
