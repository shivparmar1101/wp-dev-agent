from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Request

from backend.ai.analyzer import RepositoryAnalyzer
from backend.ai.provider import (
    AIAuthError,
    AIError,
    AIRateLimitError,
    AIServerError,
    AITimeoutError,
    AIUnavailableError,
)
from backend.models.analysis import AnalysisResponse, ChatMessage, ChatRequest, ChatResponse
from backend.storage.scans import ChatStore, ProjectStore

from .deps import SearchDep, SessionDep, enforce_rate_limit

router = APIRouter(prefix="/chat", tags=["chat"])


def _status_for(exc: AIError) -> int:
    if isinstance(exc, AIRateLimitError):
        return 429
    if isinstance(exc, (AIAuthError, AIServerError)):
        return 502
    if isinstance(exc, AITimeoutError):
        return 504
    if isinstance(exc, AIUnavailableError):
        return 503
    return 502


@router.post("/{owner}/{repo}", response_model=ChatResponse)
async def chat(
    owner: str,
    repo: str,
    request: Request,
    session: SessionDep,
    search: SearchDep,
    body: ChatRequest,
) -> ChatResponse:
    enforce_rate_limit(request, "chat", session)

    provider = getattr(request.app.state, "ai_provider", None)
    if provider is None or not provider.configured:
        raise HTTPException(
            status_code=503,
            detail=(
                "The AI provider is not configured. Set AI_PROVIDER and AI_API_KEY "
                "in your .env file (or AI_PROVIDER=mock for retrieval-only mode)."
            ),
        )

    analyzer = RepositoryAnalyzer(search, provider)
    project = ProjectStore().get(owner, repo)

    try:
        analysis = await analyzer.answer(
            owner,
            repo,
            body.message,
            history=body.history,
            project_summary=project,
        )
    except LookupError:
        raise HTTPException(
            status_code=409,
            detail=(
                "Repository index not available. Analyze the repository before "
                "asking AI questions about it."
            ),
        ) from None
    except AIError as exc:
        raise HTTPException(status_code=_status_for(exc), detail=exc.user_message()) from exc

    conversation_id = body.conversation_id or uuid.uuid4().hex
    store = ChatStore()
    try:
        store.append_messages(
            owner,
            repo,
            conversation_id,
            [
                ChatMessage(role="user", content=body.message),
                ChatMessage(
                    role="assistant",
                    content=analysis.explanation or analysis.issue or analysis.raw,
                ),
            ],
        )
        store.save_analysis(
            owner=owner,
            repo=repo,
            conversation_id=conversation_id,
            question=body.message,
            analysis=analysis,
        )
    except Exception:  # pragma: no cover - persistence must not break chat
        request.app.state  # no-op reference keeps mypy quiet

    return ChatResponse(conversation_id=conversation_id, analysis=analysis)


@router.get("/{owner}/{repo}/history")
async def chat_history(
    owner: str,
    repo: str,
    session: SessionDep,
    limit: int = 30,
) -> list[dict]:
    return ChatStore().recent_for(owner, repo, limit=min(limit, 100))
