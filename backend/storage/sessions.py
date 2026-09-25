from __future__ import annotations

import secrets
from dataclasses import dataclass

from backend.config import Settings, get_settings
from backend.utils.helpers import iso, parse_iso, utcnow
from backend.utils.logging import get_logger
from backend.utils.security import TokenCipher

from . import db

logger = get_logger(__name__)


@dataclass
class SessionRecord:
    id: str
    github_login: str
    github_name: str | None
    github_avatar: str | None
    access_token: str
    scope: str | None
    created_at: str
    expires_at: str

    @property
    def public(self) -> dict[str, object]:
        """Safe representation - never includes the access token."""
        return {
            "login": self.github_login,
            "name": self.github_name,
            "avatar": self.github_avatar,
            "scope": self.scope,
            "created_at": self.created_at,
        }


class SessionStore:
    """Server-side sessions. The browser only ever receives an opaque id."""

    def __init__(self, settings: Settings | None = None, cipher: TokenCipher | None = None):
        self.settings = settings or get_settings()
        self.cipher = cipher or TokenCipher(
            self.settings.secret_key, self.settings.sqlite_path().parent
        )

    def create(
        self,
        *,
        login: str,
        name: str | None,
        avatar: str | None,
        token: str,
        scope: str | None,
    ) -> SessionRecord:
        session_id = secrets.token_urlsafe(32)
        now = utcnow()
        expires = now.timestamp() + self.settings.session_ttl_seconds
        from datetime import datetime, timezone

        expires_at = datetime.fromtimestamp(expires, tz=timezone.utc)
        db.execute(
            "INSERT INTO sessions (id, github_login, github_name, github_avatar,"
            " access_token, scope, created_at, expires_at) VALUES (?,?,?,?,?,?,?,?)",
            (
                session_id,
                login,
                name,
                avatar,
                self.cipher.encrypt(token),
                scope,
                iso(now),
                iso(expires_at),
            ),
        )
        return SessionRecord(
            id=session_id,
            github_login=login,
            github_name=name,
            github_avatar=avatar,
            access_token=token,
            scope=scope,
            created_at=iso(now),
            expires_at=iso(expires_at),
        )

    def get(self, session_id: str | None) -> SessionRecord | None:
        if not session_id:
            return None
        row = db.query_one("SELECT * FROM sessions WHERE id = ?", (session_id,))
        if row is None:
            return None
        expires = parse_iso(row["expires_at"])
        if expires is not None and expires < utcnow():
            self.delete(session_id)
            return None
        token = self.cipher.decrypt(row["access_token"])
        if not token:
            self.delete(session_id)
            return None
        return SessionRecord(
            id=row["id"],
            github_login=row["github_login"],
            github_name=row["github_name"],
            github_avatar=row["github_avatar"],
            access_token=token,
            scope=row["scope"],
            created_at=row["created_at"],
            expires_at=row["expires_at"],
        )

    def delete(self, session_id: str) -> None:
        db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))

    def purge_expired(self) -> int:
        rows = db.query_all("SELECT id FROM sessions WHERE expires_at < ?", (iso(),))
        for row in rows:
            db.execute("DELETE FROM sessions WHERE id = ?", (row["id"],))
        return len(rows)


class OAuthStateStore:
    """Single-use, short-lived OAuth `state` values (CSRF protection)."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    def create(self) -> str:
        state = secrets.token_urlsafe(24)
        from datetime import datetime, timedelta, timezone

        now = utcnow()
        expires = now + timedelta(seconds=self.settings.oauth_state_ttl_seconds)
        db.execute(
            "INSERT INTO oauth_states (state, created_at, expires_at, used) VALUES (?,?,?,0)",
            (state, iso(now), iso(expires)),
        )
        self._purge()
        return state

    def consume(self, state: str | None) -> bool:
        """Validates and marks a state as used. Returns False on any failure."""
        if not state:
            return False
        row = db.query_one("SELECT * FROM oauth_states WHERE state = ?", (state,))
        if row is None or row["used"]:
            return False
        expires = parse_iso(row["expires_at"])
        if expires is None or expires < utcnow():
            return False
        db.execute("UPDATE oauth_states SET used = 1 WHERE state = ?", (state,))
        return True

    def _purge(self) -> None:
        db.execute("DELETE FROM oauth_states WHERE expires_at < ?", (iso(),))
