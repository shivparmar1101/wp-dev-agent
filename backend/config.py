from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_IGNORED_PATHS = (
    ".git,.hg,.svn,node_modules,vendor,dist,build,.cache,.next,.nuxt,.output,"
    "coverage,.idea,.vscode,.github,.gitlab,.circleci,__pycache__,.venv,venv,"
    ".pytest_cache,.mypy_cache,.ruff_cache,bower_components,.yarn,.pnpm-store,"
    "target,out,tmp,temp,.turbo,.parcel-cache,.sass-cache,wp-content/cache,"
    "wp-content/uploads,wp-content/upgrade,wp-content/backup*"
)


class Settings(BaseSettings):
    """Application settings loaded from environment variables / `.env`."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Application -------------------------------------------------------
    app_name: str = "WP Dev Agent"
    environment: str = "development"
    debug: bool = False
    log_level: str = "INFO"
    frontend_url: str = "http://localhost:3000"
    backend_url: str = "http://localhost:8000"
    api_prefix: str = "/api"

    # --- GitHub ------------------------------------------------------------
    github_client_id: str = ""
    github_client_secret: str = ""
    github_redirect_uri: str = "http://localhost:8000/api/auth/callback"
    github_scope: str = "repo read:user"
    github_api_url: str = "https://api.github.com"
    github_web_url: str = "https://github.com"

    # --- AI ----------------------------------------------------------------
    ai_provider: str = "openai"
    ai_api_key: str = ""
    ai_model: str = "gpt-4o-mini"
    ai_base_url: str = ""
    ai_embedding_model: str = "text-embedding-3-small"
    ai_temperature: float = 0.1
    ai_max_tokens: int = 2048
    ai_timeout_seconds: float = 60.0
    ai_context_files: int = 8
    ai_context_chunks: int = 14
    ai_context_char_budget: int = 14000

    # --- Persistence -------------------------------------------------------
    database_url: str = "sqlite:///./data/wp_dev_agent.db"
    secret_key: str = ""
    session_cookie_name: str = "wpdev_session"
    session_ttl_seconds: int = 60 * 60 * 24 * 7
    oauth_state_ttl_seconds: int = 600

    # --- Scanning ----------------------------------------------------------
    ignored_paths: str = DEFAULT_IGNORED_PATHS
    max_file_bytes: int = 1_500_000
    max_index_file_bytes: int = 400_000
    max_indexed_files: int = 2500
    max_tree_nodes: int = 6000
    scan_read_budget_bytes: int = 4_000_000
    chunk_max_lines: int = 120
    chunk_overlap_lines: int = 20
    chunk_max_chars: int = 6000
    max_search_results: int = 25

    # --- Rate limiting -----------------------------------------------------
    rate_limit_enabled: bool = True
    rate_limit_requests: int = 60
    rate_limit_window_seconds: int = 60
    chat_rate_limit_requests: int = 15
    chat_rate_limit_window_seconds: int = 60

    # --- Misc --------------------------------------------------------------
    http_user_agent: str = "wp-dev-agent/1.0"

    @field_validator("ignored_paths", mode="before")
    @classmethod
    def _coerce_ignored(cls, value: object) -> object:
        if isinstance(value, (list, tuple, set)):
            return ",".join(str(v) for v in value)
        return value

    def ignored_path_set(self) -> set[str]:
        """Normalized set of ignored directory/path fragments."""
        items = {p.strip().lower() for p in self.ignored_paths.split(",")}
        return {p for p in items if p}

    def sqlite_path(self) -> Path:
        """Resolve the SQLite path from `DATABASE_URL`."""
        url = self.database_url.strip()
        prefix = "sqlite:///"
        if not url.startswith(prefix):
            raise ValueError(
                "Only sqlite:/// DATABASE_URL values are supported in the "
                f"Foundation MVP (received: {url!r})."
            )
        raw = url[len(prefix) :] or "./data/wp_dev_agent.db"
        return Path(raw).expanduser()

    @property
    def github_configured(self) -> bool:
        return bool(self.github_client_id and self.github_client_secret)

    @property
    def ai_configured(self) -> bool:
        if self.ai_provider.lower() == "mock":
            return True
        return bool(self.ai_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    """Used by tests that mutate the environment."""
    get_settings.cache_clear()
