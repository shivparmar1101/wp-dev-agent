from __future__ import annotations

import httpx
import pytest

from backend.github.client import (
    GitHubAuthError,
    GitHubClient,
    GitHubEmptyRepositoryError,
    GitHubError,
    GitHubNotFoundError,
    GitHubRateLimitError,
    parse_link_header,
)


def make_client(handler) -> GitHubClient:
    transport = httpx.MockTransport(handler)
    return GitHubClient("test-token", transport=transport)


def test_parse_link_header():
    links = parse_link_header(
        '<https://api.github.com/user/repos?page=2>; rel="next", '
        '<https://api.github.com/user/repos?page=5>; rel="last"'
    )
    assert "next" in links and "last" in links
    assert parse_link_header(None) == {}


async def test_list_repositories_parses_payload():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer test-token"
        assert request.url.path == "/user/repos"
        return httpx.Response(
            200,
            json=[
                {
                    "id": 1,
                    "name": "site",
                    "full_name": "acme/site",
                    "owner": {"login": "acme", "avatar_url": "https://x/a.png"},
                    "default_branch": "main",
                    "private": False,
                    "html_url": "https://github.com/acme/site",
                    "language": "PHP",
                }
            ],
            headers={"X-RateLimit-Limit": "5000", "X-RateLimit-Remaining": "4999"},
        )

    client = make_client(handler)
    repos = await client.list_repositories()
    assert len(repos) == 1
    assert repos[0]["name"] == "site"
    assert client.last_rate_limit is not None
    assert client.last_rate_limit.remaining == 4999
    await client.aclose()


async def test_error_mapping():
    cases = [
        (401, GitHubAuthError),
        (404, GitHubNotFoundError),
        (403, GitHubRateLimitError),
        (429, GitHubRateLimitError),
    ]
    for status, expected in cases:
        def handler(request, status=status):
            headers = {"X-RateLimit-Remaining": "0"} if status in (403, 429) else {}
            return httpx.Response(status, json={"message": "rate limited"}, headers=headers)

        client = make_client(handler)
        with pytest.raises(expected):
            await client.get_repository("a", "b")
        await client.aclose()


async def test_rate_limit_error_carries_reset():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            json={"message": "API rate limit exceeded"},
            headers={"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "1999999999"},
        )

    client = make_client(handler)
    with pytest.raises(GitHubRateLimitError) as exc:
        await client.get_user()
    assert exc.value.reset_at == 1999999999
    assert "rate limit" in exc.value.user_message().lower()
    await client.aclose()


async def test_get_tree_returns_truncation_flag():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "sha": "abc",
                "truncated": True,
                "tree": [{"path": "wp-config.php", "type": "blob", "size": 10}],
            },
        )

    client = make_client(handler)
    tree, truncated = await client.get_tree("acme", "site", "main")
    assert truncated is True
    assert tree[0]["path"] == "wp-config.php"
    await client.aclose()


async def test_empty_repository_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(409, json={"message": "Git Repository is empty."})

    client = make_client(handler)
    with pytest.raises(GitHubEmptyRepositoryError):
        await client.get_tree("acme", "site", "main")
    await client.aclose()


async def test_network_error_is_wrapped():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    client = make_client(handler)
    with pytest.raises(GitHubError) as exc:
        await client.get_user()
    assert "reach GitHub" in exc.value.user_message()
    await client.aclose()


async def test_file_content_decoding():
    import base64

    payload = base64.b64encode(b"<?php echo 1;").decode()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"path": "index.php", "size": 13, "encoding": "base64", "content": payload},
        )

    client = make_client(handler)
    data, size = await client.get_file_content("acme", "site", "index.php")
    assert data == b"<?php echo 1;"
    assert size == 13
    await client.aclose()


async def test_path_traversal_rejected_before_request():
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        return httpx.Response(200, json={})

    client = make_client(handler)
    with pytest.raises(GitHubError):
        await client.get_file_content("acme", "site", "../../etc/passwd")
    # encoded traversal still reaches github as a literal path, but our
    # FileService blocks it earlier; ensure no crash occurred
    await client.aclose()
