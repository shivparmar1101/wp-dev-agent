from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.config import get_settings, reset_settings_cache
from backend.indexing.indexer import RepositoryIndexer, registry
from backend.storage import db
from backend.storage.sessions import SessionStore


class FakeGitHubClient:
    """Stand-in for GitHubClient so API tests never touch the network."""

    repositories = [
        {
            "id": 1,
            "name": "client-wordpress-site",
            "full_name": "acme/client-wordpress-site",
            "owner": {"login": "acme", "avatar_url": "https://x/a.png"},
            "description": "WordPress site",
            "private": False,
            "fork": False,
            "archived": False,
            "visibility": "public",
            "default_branch": "main",
            "language": "PHP",
            "html_url": "https://github.com/acme/client-wordpress-site",
            "updated_at": "2026-01-01T00:00:00Z",
            "pushed_at": "2026-01-01T00:00:00Z",
            "size": 100,
            "stargazers_count": 3,
            "topics": ["wordpress"],
        }
    ]

    def __init__(self, *args, **kwargs):
        self.last_rate_limit = None
        self.last_links = {}

    async def aclose(self):  # pragma: no cover
        return None

    async def get_user(self):
        return {"login": "octo", "name": "Octo", "avatar_url": "https://x/o.png"}

    async def list_repositories(self, **kwargs):
        return list(self.repositories)

    async def search_repositories(self, query, **kwargs):
        return list(self.repositories)

    async def get_repository(self, owner, repo):
        return {
            "name": repo,
            "full_name": f"{owner}/{repo}",
            "default_branch": "main",
            "description": "demo",
        }

    async def get_file_content(self, owner, repo, path, ref=None):
        raise AssertionError("should not be reached in these tests")


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/api.db")
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("GITHUB_CLIENT_ID", "cid")
    monkeypatch.setenv("GITHUB_CLIENT_SECRET", "sec")
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "false")
    monkeypatch.setenv("AI_PROVIDER", "mock")
    monkeypatch.setenv("ENVIRONMENT", "test")
    reset_settings_cache()
    db.reset_initialized_flag()

    from backend.main import create_app

    application = create_app()

    import backend.api.deps as deps

    monkeypatch.setattr(deps, "GitHubClient", FakeGitHubClient)
    registry.clear()

    yield application

    registry.clear()
    reset_settings_cache()
    db.reset_initialized_flag()


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def auth_client(client):
    session = SessionStore().create(
        login="octo",
        name="Octo",
        avatar="https://x/o.png",
        token="fake-token",
        scope="repo",
    )
    client.cookies.set(get_settings().session_cookie_name, session.id)
    return client


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["github_configured"] is True
    assert payload["ai_provider"] == "mock"


def test_me_anonymous(client):
    response = client.get("/api/auth/me")
    assert response.status_code == 200
    assert response.json() == {"authenticated": False, "user": None}


def test_me_authenticated(auth_client):
    response = auth_client.get("/api/auth/me")
    payload = response.json()
    assert payload["authenticated"] is True
    assert payload["user"]["login"] == "octo"
    assert "access_token" not in str(payload)


def test_repositories_requires_session(client):
    response = client.get("/api/repositories")
    assert response.status_code == 401


def test_list_repositories_authenticated(auth_client):
    response = auth_client.get("/api/repositories")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total_returned"] == 1
    repo = payload["repositories"][0]
    assert repo["full_name"] == "acme/client-wordpress-site"
    assert repo["default_branch"] == "main"


def test_logout_clears_session(auth_client):
    assert auth_client.get("/api/auth/me").json()["authenticated"] is True
    response = auth_client.post("/api/auth/logout")
    assert response.status_code == 200
    assert auth_client.get("/api/auth/me").json()["authenticated"] is False


def test_login_redirects_to_github(client):
    response = client.get("/api/auth/login", follow_redirects=False)
    assert response.status_code == 307
    location = response.headers["location"]
    assert "github.com/login/oauth/authorize" in location
    assert "client_id=cid" in location
    assert "state=" in location


def test_project_not_scanned_yet(auth_client):
    response = auth_client.get("/api/projects/acme/client-wordpress-site")
    assert response.status_code == 404
    assert "not been analyzed" in response.json()["detail"]


def test_projects_list_empty(auth_client):
    assert auth_client.get("/api/projects").json() == []


def test_search_requires_index(auth_client):
    response = auth_client.post(
        "/api/search/acme/client-wordpress-site", json={"query": "header"}
    )
    assert response.status_code == 409
    assert "Analyze the repository" in response.json()["detail"]


def test_chat_requires_index(auth_client):
    response = auth_client.post(
        "/api/chat/acme/client-wordpress-site", json={"message": "why is the header broken?"}
    )
    assert response.status_code == 409


def test_chat_without_session(client):
    response = client.post("/api/chat/acme/site", json={"message": "hello"})
    assert response.status_code == 401


def test_chat_with_index_and_mock_provider(auth_client, wp_scan, dict_reader, settings):
    import asyncio

    from backend.indexing.search import SearchService

    built = asyncio.run(RepositoryIndexer(dict_reader.read, settings).build(wp_scan))
    registry.put(built)
    auth_client.app.state.search_service = SearchService(registry=registry)

    response = auth_client.post(
        "/api/chat/acme/client-wordpress-site",
        json={"message": "Why is the mobile header overflowing?"},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["conversation_id"]
    analysis = payload["analysis"]
    assert analysis["relevant_files"]
    assert analysis["provider"] == "mock"
    for ref in analysis["relevant_files"]:
        assert ref["file_path"] in built.files


def test_file_endpoint_blocks_traversal(auth_client):
    response = auth_client.get(
        "/api/projects/acme/site/file", params={"path": "../../etc/passwd"}
    )
    assert response.status_code == 400


def test_file_endpoint_blocks_sensitive_files(auth_client):
    response = auth_client.get("/api/projects/acme/site/file", params={"path": ".env"})
    assert response.status_code == 403
    assert "protected" in response.json()["detail"]


def test_scan_status_missing(auth_client):
    response = auth_client.get("/api/scan/acme/client-wordpress-site/status")
    assert response.status_code == 404


def test_error_shape_has_detail(client):
    response = client.get("/api/repositories")
    assert "detail" in response.json()
