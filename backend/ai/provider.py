from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from backend.config import Settings, get_settings


@dataclass
class AIMessage:
    role: str  # system | user | assistant
    content: str


@dataclass
class AIResult:
    text: str
    model: str
    provider: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    finish_reason: str | None = None
    raw: dict = field(default_factory=dict, repr=False)


class AIError(Exception):
    kind = "ai_error"

    def __init__(self, message: str, detail: str | None = None):
        super().__init__(message)
        self.message = message
        self.detail = detail

    def user_message(self) -> str:
        return self.message


class AIAuthError(AIError):
    kind = "ai_auth_error"

    def user_message(self) -> str:
        return "The AI provider rejected the configured API key. Check AI_API_KEY."


class AIRateLimitError(AIError):
    kind = "ai_rate_limit"

    def user_message(self) -> str:
        return "The AI provider is rate limiting requests. Please wait and try again."


class AIServerError(AIError):
    """The provider answered 5xx / overload after retries were exhausted."""

    kind = "ai_server_error"

    def user_message(self) -> str:
        return "The AI provider is temporarily unavailable. Please try again shortly."


class AITimeoutError(AIError):
    kind = "ai_timeout"

    def user_message(self) -> str:
        return "The AI request timed out. Please try again."


class AIUnavailableError(AIError):
    kind = "ai_unavailable"

    def user_message(self) -> str:
        return (
            "The AI provider is not configured. Set AI_PROVIDER and AI_API_KEY "
            "in your .env file (or use AI_PROVIDER=mock for local development)."
        )


class AIProvider(ABC):
    """Abstract LLM provider. Implementations must be swappable via env vars."""

    name: str = "base"
    requires_key: bool = True

    def __init__(self, settings: Settings):
        self.settings = settings
        self.model = settings.ai_model

    @abstractmethod
    async def complete(
        self,
        messages: list[AIMessage],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AIResult:
        raise NotImplementedError

    def supports_embeddings(self) -> bool:
        return False

    async def embed(self, texts: list[str]) -> list[list[float]] | None:  # pragma: no cover
        return None

    @property
    def configured(self) -> bool:
        if self.requires_key and not self.settings.ai_api_key:
            if self.name == "openai" and self.settings.ai_base_url:
                return True  # local / self-hosted OpenAI-compatible endpoints
            return False
        return True


def create_provider(settings: Settings | None = None) -> AIProvider:
    from .client import AnthropicProvider, GeminiProvider, MockProvider, OpenAIProvider

    settings = settings or get_settings()
    registry: dict[str, type[AIProvider]] = {
        "openai": OpenAIProvider,
        "anthropic": AnthropicProvider,
        "gemini": GeminiProvider,
        "mock": MockProvider,
    }
    key = (settings.ai_provider or "openai").strip().lower()
    provider_cls = registry.get(key)
    if provider_cls is None:
        raise AIUnavailableError(
            f"Unknown AI provider {key!r}. Supported: {', '.join(sorted(registry))}."
        )
    return provider_cls(settings)
