from __future__ import annotations

import asyncio

from backend.config import Settings, get_settings
from backend.models.file import FileContent
from backend.utils.logging import get_logger
from backend.utils.security import (
    find_secret_patterns,
    is_blocked_path,
    is_safe_path,
    redact_secrets,
)

from .client import GitHubClient, GitHubError, GitHubNotFoundError

logger = get_logger(__name__)

def decode_content(data: bytes) -> tuple[str, str] | None:
    """Decode bytes as text. Returns None when the payload looks binary."""
    if not data:
        return "", "utf-8"
    sample = data[:8192]
    if b"\x00" in sample:
        return None
    try:
        return data.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        pass
    try:
        return data.decode("utf-8-sig"), "utf-8-sig"
    except UnicodeDecodeError:
        return None


class FileService:
    """Reads repository files with size, path and binary protections."""

    def __init__(self, client: GitHubClient, settings: Settings | None = None):
        self.client = client
        self.settings = settings or get_settings()
        self._semaphore = asyncio.Semaphore(6)

    async def read_bytes(
        self, owner: str, repo: str, path: str, ref: str | None = None
    ) -> tuple[bytes, int]:
        if not is_safe_path(path):
            raise GitHubError("Invalid file path.", status=400)
        if is_blocked_path(path):
            raise GitHubError("This file is protected and cannot be read.", status=403)
        async with self._semaphore:
            data, size = await self.client.get_file_content(owner, repo, path, ref)
        if size > self.settings.max_file_bytes or len(data) > self.settings.max_file_bytes:
            raise GitHubError(
                f"File exceeds the {self.settings.max_file_bytes} byte read limit.",
                status=413,
            )
        return data, size

    async def read_text(
        self, owner: str, repo: str, path: str, ref: str | None = None
    ) -> str | None:
        """Returns file text or None when the file is binary/unreadable."""
        try:
            data, _size = await self.read_bytes(owner, repo, path, ref)
        except GitHubNotFoundError:
            return None
        except GitHubError:
            return None
        decoded = decode_content(data)
        if decoded is None:
            return None
        return decoded[0]

    async def read_file(
        self,
        owner: str,
        repo: str,
        path: str,
        ref: str | None = None,
        *,
        for_ai: bool = False,
    ) -> FileContent | None:
        if not is_safe_path(path) or is_blocked_path(path):
            return None
        data, size = await self.read_bytes(owner, repo, path, ref)
        decoded = decode_content(data)
        if decoded is None:
            return None
        content, encoding = decoded
        truncated = False
        limit = self.settings.max_index_file_bytes if for_ai else self.settings.max_file_bytes
        if len(content) > limit:
            content = content[:limit]
            truncated = True
        redacted = False
        if for_ai:
            aggressive = True
        else:
            aggressive = False
        scrubbed = redact_secrets(content, aggressive=aggressive)
        if scrubbed != content:
            redacted = True
            content = scrubbed
        return FileContent(
            path=path,
            content=content,
            size=size,
            encoding=encoding,
            truncated=truncated,
            redacted=redacted,
            ref=ref,
        )

    async def read_many(
        self,
        owner: str,
        repo: str,
        paths: list[str],
        ref: str | None = None,
        *,
        max_bytes: int | None = None,
        batch_size: int = 6,
    ) -> dict[str, str]:
        """Reads several files concurrently. Skips blocked/oversized/binary files."""
        from backend.utils.helpers import chunked

        budget = max_bytes if max_bytes is not None else self.settings.scan_read_budget_bytes
        results: dict[str, str] = {}
        spent = 0
        for batch in chunked(list(paths), batch_size):
            if spent > budget:
                break
            texts = await asyncio.gather(
                *(self.read_text(owner, repo, path, ref) for path in batch),
                return_exceptions=True,
            )
            for path, text in zip(batch, texts):
                if isinstance(text, BaseException) or text is None:
                    continue
                if spent + len(text) > budget:
                    continue
                spent += len(text)
                results[path] = text
        if spent >= budget:
            logger.info("Scan read budget reached (%s bytes)", budget)
        return results

    def secret_scan(self, content: str, *, aggressive: bool = True) -> list[str]:
        return find_secret_patterns(content, aggressive=aggressive)
