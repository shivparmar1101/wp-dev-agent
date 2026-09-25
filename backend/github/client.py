from __future__ import annotations

import asyncio
import json
import re
from typing import Any

import httpx

from backend.models.repository import RateLimitInfo
from backend.utils.logging import get_logger

logger = get_logger(__name__)


class GitHubError(Exception):
    """Base class for GitHub API failures with a user friendly message."""

    kind = "github_error"

    def __init__(self, message: str, status: int | None = None, detail: str | None = None):
        super().__init__(message)
        self.message = message
        self.status = status
        self.detail = detail

    def user_message(self) -> str:
        return self.message


class GitHubAuthError(GitHubError):
    kind = "auth_error"

    def user_message(self) -> str:
        return (
            "Your GitHub session is no longer valid. "
            "Please reconnect GitHub and try again."
        )


class GitHubNotFoundError(GitHubError):
    kind = "not_found"

    def user_message(self) -> str:
        return (
            "Unable to access this repository.\n\nPossible reasons:\n"
            "- You do not have permission.\n- The repository was deleted.\n"
            "- GitHub authentication expired.\n\n"
            "Please reconnect GitHub and try again."
        )


class GitHubForbiddenError(GitHubError):
    kind = "forbidden"

    def user_message(self) -> str:
        return (
            "GitHub denied access to this resource. Your token may be missing "
            "the required scope, or the repository is not accessible to you."
        )


class GitHubRateLimitError(GitHubError):
    kind = "rate_limit"

    def __init__(self, message: str, status: int | None = None,
                 reset_at: int | None = None, detail: str | None = None):
        super().__init__(message, status=status, detail=detail)
        self.reset_at = reset_at

    def user_message(self) -> str:
        if self.reset_at:
            import datetime as _dt

            try:
                when = _dt.datetime.fromtimestamp(self.reset_at, tz=_dt.timezone.utc)
                stamp = when.strftime("%H:%M UTC")
            except (OverflowError, OSError, ValueError):
                stamp = "shortly"
            return (
                f"GitHub API rate limit reached. The limit resets at {stamp}. "
                "Please wait a moment and try again."
            )
        return "GitHub API rate limit reached. Please wait a moment and try again."


class GitHubEmptyRepositoryError(GitHubError):
    kind = "empty_repository"

    def user_message(self) -> str:
        return "This repository is empty, so there is nothing to analyze yet."


class GitHubNetworkError(GitHubError):
    kind = "network_error"

    def user_message(self) -> str:
        return "Could not reach GitHub. Check your connection and try again."


_LINK_RE = re.compile(r'<([^>]+)>;\s*rel="([^"]+)"')


def parse_link_header(value: str | None) -> dict[str, str]:
    links: dict[str, str] = {}
    if not value:
        return links
    for match in _LINK_RE.finditer(value):
        links[match.group(2)] = match.group(1)
    return links


class GitHubClient:
    """Thin async wrapper around the GitHub REST API."""

    def __init__(
        self,
        token: str,
        *,
        api_url: str = "https://api.github.com",
        user_agent: str = "wp-dev-agent/1.0",
        timeout: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.token = token
        self.api_url = api_url.rstrip("/")
        self.last_rate_limit: RateLimitInfo | None = None
        self.last_links: dict[str, str] = {}
        self._client = httpx.AsyncClient(
            base_url=self.api_url,
            timeout=timeout,
            transport=transport,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": user_agent,
            },
            follow_redirects=False,
        )

    async def __aenter__(self) -> "GitHubClient":
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        try:
            await self._client.aclose()
        except Exception:  # pragma: no cover
            pass

    # -- low level ---------------------------------------------------------
    def _capture_headers(self, response: httpx.Response) -> None:
        headers = response.headers
        if "x-ratelimit-limit" in headers:
            def _int(key: str) -> int | None:
                raw = headers.get(key)
                try:
                    return int(raw) if raw is not None else None
                except ValueError:
                    return None

            self.last_rate_limit = RateLimitInfo(
                limit=_int("x-ratelimit-limit"),
                remaining=_int("x-ratelimit-remaining"),
                reset=_int("x-ratelimit-reset"),
                used=_int("x-ratelimit-used"),
                resource=headers.get("x-ratelimit-resource"),
            )
        self.last_links = parse_link_header(headers.get("link"))

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        retries: int = 2,
    ) -> httpx.Response:
        attempt = 0
        last_error: Exception | None = None
        while attempt <= retries:
            try:
                response = await self._client.request(
                    method, path, params=params, json=json_body
                )
            except httpx.TimeoutException as exc:
                last_error = GitHubNetworkError("GitHub request timed out.", detail=str(exc))
            except httpx.HTTPError as exc:
                last_error = GitHubNetworkError("GitHub request failed.", detail=str(exc))
            else:
                self._capture_headers(response)
                if response.status_code < 400:
                    return response
                if response.status_code in (502, 503, 504) and attempt < retries:
                    await asyncio.sleep(0.6 * (attempt + 1))
                    attempt += 1
                    continue
                raise self._to_error(response)
            attempt += 1
            if attempt > retries:
                break
            await asyncio.sleep(0.5 * attempt)
        if last_error is not None:
            raise last_error
        raise GitHubNetworkError("GitHub request failed.")

    def _to_error(self, response: httpx.Response) -> GitHubError:
        status = response.status_code
        try:
            payload = response.json()
            message = payload.get("message", "") if isinstance(payload, dict) else ""
            errors = payload.get("errors") if isinstance(payload, dict) else None
            detail = json.dumps(errors) if errors else None
        except Exception:
            message = ""
            detail = response.text[:500] or None

        if status in (401,):
            return GitHubAuthError(message or "Unauthorized", status=status, detail=detail)
        if status == 404:
            return GitHubNotFoundError(message or "Not found", status=status, detail=detail)
        if status == 429 or status == 403:
            remaining = response.headers.get("x-ratelimit-remaining")
            reset_raw = response.headers.get("x-ratelimit-reset")
            reset_at: int | None = None
            try:
                reset_at = int(reset_raw) if reset_raw else None
            except ValueError:
                reset_at = None
            lowered = (message or "").lower()
            if remaining == "0" or "rate limit" in lowered or "secondary rate limit" in lowered:
                return GitHubRateLimitError(
                    message or "Rate limited", status=status, reset_at=reset_at, detail=detail
                )
            return GitHubForbiddenError(message or "Forbidden", status=status, detail=detail)
        if status == 409:
            if "empty" in (message or "").lower():
                return GitHubEmptyRepositoryError(message, status=status, detail=detail)
            return GitHubError(message or "Conflict", status=status, detail=detail)
        if status == 422:
            return GitHubError(message or "Unprocessable request", status=status, detail=detail)
        return GitHubError(message or f"GitHub error {status}", status=status, detail=detail)

    async def get_json(
        self, path: str, params: dict[str, Any] | None = None
    ) -> Any:
        response = await self.request("GET", path, params=params)
        if response.status_code == 204 or not response.content:
            return None
        return response.json()

    # -- endpoints ---------------------------------------------------------
    async def get_user(self) -> dict[str, Any]:
        data = await self.get_json("/user")
        if not isinstance(data, dict):
            raise GitHubError("Unexpected GitHub response for /user")
        return data

    async def list_repositories(
        self,
        *,
        page: int = 1,
        per_page: int = 30,
        sort: str = "updated",
        visibility: str = "all",
    ) -> list[dict[str, Any]]:
        data = await self.get_json(
            "/user/repos",
            params={
                "sort": sort,
                "direction": "desc",
                "page": page,
                "per_page": per_page,
                "visibility": visibility,
                "affiliation": "owner,collaborator,organization_member",
            },
        )
        if not isinstance(data, list):
            raise GitHubError("Unexpected GitHub response for /user/repos")
        return data

    async def search_repositories(
        self, query: str, *, page: int = 1, per_page: int = 30
    ) -> list[dict[str, Any]]:
        data = await self.get_json(
            "/search/repositories",
            params={"q": query, "page": page, "per_page": per_page, "sort": "updated"},
        )
        if not isinstance(data, dict):
            raise GitHubError("Unexpected GitHub response for /search/repositories")
        items = data.get("items", [])
        return items if isinstance(items, list) else []

    async def get_repository(self, owner: str, repo: str) -> dict[str, Any]:
        data = await self.get_json(f"/repos/{owner}/{repo}")
        if not isinstance(data, dict):
            raise GitHubError("Unexpected GitHub response for repository metadata")
        return data

    async def get_tree(
        self, owner: str, repo: str, ref: str, *, recursive: bool = True
    ) -> tuple[list[dict[str, Any]], bool]:
        params: dict[str, Any] = {"ref": ref}
        if recursive:
            params["recursive"] = "1"
        try:
            data = await self.get_json(f"/repos/{owner}/{repo}/git/trees/{ref}", params=params)
        except GitHubNotFoundError:
            # Some repositories need the branch resolved first.
            branch = await self.get_json(f"/repos/{owner}/{repo}/branches/{ref}")
            commit_sha = branch["commit"]["sha"]  # type: ignore[index]
            data = await self.get_json(
                f"/repos/{owner}/{repo}/git/trees/{commit_sha}", params=params
            )
        if not isinstance(data, dict):
            raise GitHubError("Unexpected GitHub response for git tree")
        tree = data.get("tree")
        if not isinstance(tree, list):
            raise GitHubError("Git tree response did not include a tree")
        return tree, bool(data.get("truncated"))

    async def get_branches(self, owner: str, repo: str) -> list[dict[str, Any]]:
        data = await self.get_json(f"/repos/{owner}/{repo}/branches", params={"per_page": 100})
        return data if isinstance(data, list) else []

    async def get_file_metadata(
        self, owner: str, repo: str, path: str, ref: str | None = None
    ) -> dict[str, Any]:
        params = {"ref": ref} if ref else None
        data = await self.get_json(
            f"/repos/{owner}/{repo}/contents/{_encode_path(path)}", params=params
        )
        if isinstance(data, list):
            raise GitHubError("Path is a directory, not a file", status=400)
        if not isinstance(data, dict):
            raise GitHubError("Unexpected GitHub response for file contents")
        return data

    async def get_file_content(
        self, owner: str, repo: str, path: str, ref: str | None = None
    ) -> tuple[bytes, int]:
        """Returns raw bytes and the reported file size."""
        meta = await self.get_file_metadata(owner, repo, path, ref)
        size = int(meta.get("size") or 0)
        encoding = meta.get("encoding")
        content = meta.get("content")
        if encoding == "base64" and isinstance(content, str):
            import base64

            cleaned = re.sub(r"\s+", "", content)
            try:
                return base64.b64decode(cleaned), size
            except Exception as exc:
                raise GitHubError("Failed to decode file content", detail=str(exc)) from exc
        download_url = meta.get("download_url")
        if isinstance(download_url, str) and download_url:
            response = await self.request("GET", download_url)
            return response.content, size or len(response.content)
        raise GitHubError("File content is unavailable (possibly too large for the API).")


def _encode_path(path: str) -> str:
    from urllib.parse import quote

    return "/".join(quote(segment, safe="") for segment in path.split("/"))
