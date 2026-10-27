from __future__ import annotations

from pathlib import Path

from backend.config import get_settings
from backend.utils.logging import get_logger
from backend.utils.security import is_blocked_path, is_safe_path

logger = get_logger(__name__)

#: On-disk home for website snapshots (`owner == "web"`). Each host gets a
#: directory so `/api/projects/web/<host>/file` can serve contents without a
#: GitHub token and without re-fetching the site.
SITES_DIRNAME = "sites"


def sites_root() -> Path:
    root = get_settings().sqlite_path().parent / SITES_DIRNAME
    root.mkdir(parents=True, exist_ok=True)
    return root


def save_site(hostname: str, files: dict[str, str]) -> Path:
    """Persist crawled file contents under data/sites/<hostname>/."""
    host_dir = sites_root() / hostname
    if host_dir.exists():
        for existing in host_dir.rglob("*"):
            if existing.is_file():
                existing.unlink()
    for path, content in files.items():
        target = host_dir / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8", errors="replace")
    return host_dir


def read_site_file(hostname: str, path: str) -> str | None:
    """Read one crawled file; None when absent or unsafe."""
    if not is_safe_path(path) or is_blocked_path(path):
        return None
    host_dir = (sites_root() / hostname).resolve()
    target = (host_dir / path).resolve()
    try:
        target.relative_to(host_dir)
    except ValueError:  # path escape attempt
        return None
    if not target.is_file():
        return None
    try:
        return target.read_text(encoding="utf-8", errors="replace")
    except OSError:  # pragma: no cover - defensive
        logger.warning("Could not read snapshot file %s/%s", hostname, path)
        return None
