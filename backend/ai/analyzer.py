from __future__ import annotations

import json
import re
import uuid
from typing import Sequence

from backend.config import Settings, get_settings
from backend.indexing.search import SearchService
from backend.models.analysis import (
    AnalysisResponse,
    ChatMessage,
    CodeReference,
    SearchHit,
)
from backend.utils.logging import get_logger
from backend.utils.security import looks_like_prompt_injection, redact_secrets

from .prompts import (
    PLANNER_SYSTEM_PROMPT,
    SYSTEM_PROMPT,
    build_context_blocks,
    build_plan_message,
    build_user_message,
    extract_json,
    heuristic_plan,
    parse_plan,
    project_summary_text,
)
from .provider import (
    AIError,
    AIProvider,
    AIMessage,
    AIRateLimitError,
    AIServerError,
    AITimeoutError,
)

logger = get_logger(__name__)

_FILENAME_RE = re.compile(r"[\w./-]+\.(?:php|js|ts|jsx|tsx|css|scss|less|html|json|yml|yaml|xml|md|txt)\b", re.I)


class RepositoryAnalyzer:
    """Plans a search, gathers repository context and asks the model for analysis.

    The pipeline is: question -> search plan -> repository search -> bounded
    context -> LLM -> validated structured response.
    """

    def __init__(
        self,
        search: SearchService,
        provider: AIProvider,
        settings: Settings | None = None,
    ):
        self.search = search
        self.provider = provider
        self.settings = settings or get_settings()

    # -- query planning ----------------------------------------------------
    async def plan(self, question: str) -> dict:
        fallback = heuristic_plan(question)
        if not self.settings.ai_api_key or self.provider.name == "mock":
            return fallback
        if len(question.strip()) < 25:
            return fallback
        try:
            result = await self.provider.complete(
                [
                    AIMessage(role="system", content=PLANNER_SYSTEM_PROMPT),
                    AIMessage(role="user", content=build_plan_message(question)),
                ],
                temperature=0.0,
                max_tokens=300,
            )
            plan = parse_plan(result.text)
            if plan.get("search_terms") or plan.get("exact_phrases") or plan.get("file_hints"):
                merged = dict(fallback)
                merged.update({k: v for k, v in plan.items() if v})
                return merged
        except AIError as exc:
            logger.info("Query planning fell back to heuristics: %s", exc.message)
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("Query planning failed: %s", exc)
        return fallback

    # -- retrieval ---------------------------------------------------------
    async def _retrieve(
        self, index_owner: str, index_repo: str, question: str, plan: dict
    ) -> tuple[list[SearchHit], list[str]]:
        merged: dict[tuple, SearchHit] = {}
        notes: list[str] = []

        def add(hits: list[SearchHit]) -> None:
            for hit in hits:
                key = (hit.file_path, hit.start_line, hit.end_line, hit.match_type)
                existing = merged.get(key)
                if existing is None or hit.score > existing.score:
                    merged[key] = hit

        # 1. Exact phrases (quoted strings or explicit selectors).
        phrases: list[str] = list(plan.get("exact_phrases") or [])
        for phrase in phrases[:2]:
            try:
                response = await self.search.search(
                    index_owner, index_repo, phrase, mode="exact", limit=6
                )
                add(response.hits)
                notes.extend(response.notes)
            except Exception as exc:  # pragma: no cover - defensive
                logger.debug("Exact search failed: %s", exc)

        # 2. File hints.
        for hint in list(plan.get("file_hints") or [])[:3]:
            try:
                response = await self.search.search(
                    index_owner, index_repo, hint, mode="file", limit=4
                )
                add(response.hits)
            except Exception as exc:  # pragma: no cover
                logger.debug("File search failed: %s", exc)

        # 3. Main semantic/keyword query (question + planned terms).
        terms = list(plan.get("search_terms") or [])
        main_query = question.strip()
        if terms:
            main_query = f"{main_query} {' '.join(terms)}"
        try:
            response = await self.search.search(
                index_owner, index_repo, main_query, mode="hybrid",
                limit=self.settings.max_search_results,
            )
            add(response.hits)
            notes.extend(response.notes)
        except Exception as exc:
            logger.warning("Repository search failed: %s", exc)
            notes.append("Repository search failed; the model received only the project summary.")

        ranked = sorted(merged.values(), key=lambda h: -h.score)
        return ranked, notes

    # -- main entry point --------------------------------------------------
    async def answer(
        self,
        owner: str,
        repo: str,
        question: str,
        *,
        history: Sequence[ChatMessage] = (),
        project_summary: object | None = None,
    ) -> AnalysisResponse:
        index = self.search.get_index(owner, repo)
        if index is None:
            raise LookupError("repository_index_missing")

        plan = await self.plan(question)
        hits, notes = await self._retrieve(owner, repo, question, plan)

        selected: list[SearchHit] = []
        files: list[str] = []
        for hit in hits:
            if len(selected) >= self.settings.ai_context_chunks:
                break
            if hit.file_path not in files and len(files) >= self.settings.ai_context_files:
                continue
            if hit.file_path not in files:
                files.append(hit.file_path)
            selected.append(hit)

        context_blocks: list[tuple[str, int, int, str]] = []
        for hit in selected:
            chunk = self._find_chunk(index.chunks, hit)
            if chunk is None:
                continue
            context_blocks.append(
                (hit.file_path, chunk.start_line, chunk.end_line, chunk.content)
            )

        context_text = build_context_blocks(context_blocks)
        if len(context_text) > self.settings.ai_context_char_budget:
            context_text = context_text[: self.settings.ai_context_char_budget] + "\n... (context truncated) ..."

        injection_suspects = [
            hit.file_path
            for hit in selected
            if looks_like_prompt_injection(hit.snippet or "")
        ]
        if injection_suspects:
            notes.append(
                "Some retrieved files contain instruction-like text; they were "
                "treated strictly as data."
            )

        history_pairs = [(m.role, m.content) for m in history[-6:]]
        user_message = build_user_message(
            question,
            context_text,
            project_summary=project_summary_text(project_summary),
            history=history_pairs,
        )
        messages = [
            AIMessage(role="system", content=SYSTEM_PROMPT),
            AIMessage(role="user", content=user_message),
        ]

        try:
            result = await self.provider.complete(messages)
        except (AIRateLimitError, AITimeoutError, AIServerError) as exc:
            # Quota or upstream overload: retrieval above already succeeded, so
            # answer with those results instead of failing the whole request.
            logger.warning(
                "AI analysis unavailable (%s); answering with retrieval only.",
                exc.message,
            )
            notes.append(exc.user_message())
            return self._to_response(
                json.dumps(self._degraded_payload(question, exc)),
                question=question,
                index_files=set(index.files.keys()),
                index=index,
                search_hits=selected,
                notes=notes,
                plan=plan,
                provider_name=self.provider.name,
                model=getattr(self.provider, "model", None) or self.provider.name,
            )

        analysis = self._to_response(
            result.text,
            question=question,
            index_files=set(index.files.keys()),
            index=index,
            search_hits=selected,
            notes=notes,
            plan=plan,
            provider_name=result.provider,
            model=result.model,
        )
        return analysis

    # -- graceful degradation ----------------------------------------------
    @staticmethod
    def _degraded_payload(question: str, exc: AIError) -> dict:
        """Structured answer used when the model itself is unavailable.

        Retrieval already succeeded at this point, so the caller still sees the
        relevant files; only model reasoning is missing.
        """
        detail = f" {exc.detail}" if exc.detail else ""
        return {
            "issue": question[:400] or "Repository question received.",
            "relevant_files": [],
            "cause": (exc.user_message() + detail)[:600],
            "suggested_solution": (
                "The AI provider is temporarily unavailable, so this answer only "
                "contains the files retrieved from the repository index. Retry in "
                "a moment to get a full model analysis."
            ),
            "solution_language": None,
            "confidence": "Unknown",
            "explanation": (
                "Model reasoning was skipped because the AI provider did not "
                "answer. Search, file context gathering and secret redaction all "
                "ran normally against the repository index."
            ),
        }

    # -- response handling -------------------------------------------------
    def _find_chunk(self, chunks, hit: SearchHit):
        for chunk in chunks:
            if (
                chunk.file_path == hit.file_path
                and chunk.start_line <= (hit.start_line or 0) <= chunk.end_line
            ):
                return chunk
        for chunk in chunks:
            if chunk.file_path == hit.file_path:
                return chunk
        return None

    def _to_response(
        self,
        text: str,
        *,
        question: str,
        index_files: set[str],
        index,
        search_hits: list[SearchHit],
        notes: list[str],
        plan: dict,
        provider_name: str,
        model: str,
    ) -> AnalysisResponse:
        warnings = list(notes)
        data: dict | None = None
        try:
            data = extract_json(text)
        except ValueError:
            logger.info("Model did not return JSON; wrapping raw response")
            data = None

        relevant: list[CodeReference] = []
        if data is not None:
            issue = str(data.get("issue") or question)[:1000]
            cause = str(data.get("cause") or "")
            solution = str(data.get("suggested_solution") or "")
            explanation = str(data.get("explanation") or "")
            confidence_raw = str(data.get("confidence") or "Unknown").capitalize()
            confidence = confidence_raw if confidence_raw in ("High", "Medium", "Low") else "Unknown"
            solution_language = data.get("solution_language")
            if solution_language in (None, "none", ""):
                solution_language = None

            raw_files = data.get("relevant_files")
            dropped: list[str] = []
            if isinstance(raw_files, list):
                for item in raw_files[:10]:
                    if not isinstance(item, dict):
                        continue
                    path = str(item.get("file_path") or "").strip().lstrip("/")
                    if not path:
                        continue
                    if path not in index_files:
                        dropped.append(path)
                        continue
                    start = _safe_int(item.get("start_line"))
                    end = _safe_int(item.get("end_line"))
                    snippet = str(item.get("snippet") or "")
                    language = _language_for(index, path)
                    if not snippet:
                        snippet = self._snippet_from_index(index, path, start)
                    if start is None or end is None:
                        start, end = _lines_from_snippet(snippet)
                    relevant.append(
                        CodeReference(
                            file_path=path,
                            start_line=start,
                            end_line=end,
                            snippet=snippet[:2000],
                            language=language,
                        )
                    )
            if dropped:
                warnings.append(
                    "The model referenced files that do not exist in the index and "
                    f"they were removed: {', '.join(sorted(set(dropped))[:5])}"
                )
        else:
            issue = question[:400]
            cause = ""
            solution = ""
            explanation = text.strip()
            confidence = "Unknown"
            solution_language = None
            relevant = [
                CodeReference(
                    file_path=hit.file_path,
                    start_line=hit.start_line,
                    end_line=hit.end_line,
                    snippet=(hit.snippet or "")[:1000],
                    language=_language_for(index, hit.file_path),
                )
                for hit in search_hits[:5]
            ]
            warnings.append("The AI response could not be parsed into the standard format.")

        if not relevant and search_hits:
            for hit in search_hits[:4]:
                relevant.append(
                    CodeReference(
                        file_path=hit.file_path,
                        start_line=hit.start_line,
                        end_line=hit.end_line,
                        snippet=(hit.snippet or "")[:1000],
                        language=_language_for(index, hit.file_path),
                    )
                )

        if provider_name == "mock":
            warnings.append(
                "AI model not configured (AI_PROVIDER=mock): showing repository "
                "retrieval results without model reasoning. Set AI_API_KEY for full analysis."
            )

        files_consulted = sorted({h.file_path for h in search_hits}) or sorted(
            {r.file_path for r in relevant}
        )

        scrub = lambda value: redact_secrets(str(value), aggressive=True)  # noqa: E731

        from backend.utils.helpers import utcnow

        return AnalysisResponse(
            issue=scrub(issue),
            relevant_files=relevant,
            cause=scrub(cause),
            suggested_solution=scrub(solution),
            solution_language=solution_language,
            confidence=confidence,  # type: ignore[arg-type]
            explanation=scrub(explanation),
            raw=scrub(text),
            search_terms=list(plan.get("search_terms") or []),
            mode_used="hybrid",
            files_consulted=files_consulted,
            warnings=_unique(warnings),
            provider=provider_name,
            model=model,
            created_at=utcnow(),
        )

    @staticmethod
    def _snippet_from_index(index, path: str, start_line: int | None) -> str:
        for chunk in index.chunks:
            if chunk.file_path != path:
                continue
            if start_line is None or chunk.start_line <= start_line <= chunk.end_line:
                return chunk.content[:600]
        for chunk in index.chunks:
            if chunk.file_path == path:
                return chunk.content[:600]
        return ""


def _language_for(index, path: str) -> str | None:
    info = index.files.get(path)
    return info.language if info else None


def _safe_int(value: object) -> int | None:
    try:
        if value is None or value == "":
            return None
        parsed = int(value)  # type: ignore[arg-type]
        return parsed if parsed > 0 else None
    except (TypeError, ValueError):
        return None


def _lines_from_snippet(snippet: str) -> tuple[int | None, int | None]:
    if not snippet:
        return None, None
    count = snippet.count("\n") + 1
    return 1, max(1, count)


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result
