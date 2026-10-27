from __future__ import annotations

import re
from collections import deque
from dataclasses import dataclass, field
from typing import Awaitable, Callable
from urllib.parse import urldefrag, urljoin, urlparse

import httpx

from backend.config import Settings, get_settings
from backend.models.file import ClassifiedFile
from backend.utils.logging import get_logger
from backend.utils.security import is_blocked_path

from .file_classifier import classify
from .repository_scanner import ScanResult, build_tree

logger = get_logger(__name__)

DEFAULT_MAX_PAGES = 50
DEFAULT_MAX_BYTES = 5_000_000
DEFAULT_MAX_DEPTH = 3
DEFAULT_TIMEOUT_SECONDS = 15.0
USER_AGENT = (
    "WP-Dev-Agent-Site-Snapshot/1.0 (read-only site analysis; "
    "+https://github.com/shivparmar1101/wp-dev-agent)"
)

#: Only these content types are stored as indexable source text.
TEXT_CONTENT_TYPES = {
    "text/html",
    "application/xhtml+xml",
    "text/css",
    "text/javascript",
    "application/javascript",
    "application/x-javascript",
    "application/json",
    "text/json",
    "text/plain",
    "text/xml",
    "application/xml",
    "image/svg+xml",
}

HTML_CONTENT_TYPES = {"text/html", "application/xhtml+xml"}

#: Extensionless URLs and assets without a suffix get one from their MIME type.
_EXT_FOR_TYPE = {
    "text/css": ".css",
    "text/javascript": ".js",
    "application/javascript": ".js",
    "application/x-javascript": ".js",
    "application/json": ".json",
    "text/json": ".json",
    "text/xml": ".xml",
    "application/xml": ".xml",
    "image/svg+xml": ".svg",
    "text/plain": ".txt",
}

#: Never requested: binaries and other assets we cannot index as text.
_SKIP_SUFFIXES = {
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif", ".ico", ".bmp", ".tif",
    ".tiff", ".mp3", ".mp4", ".webm", ".ogg", ".wav", ".mov", ".avi",
    ".pdf", ".zip", ".gz", ".tar", ".rar", ".7z", ".dmg", ".exe", ".bin",
    ".woff", ".woff2", ".ttf", ".otf", ".eot", ".map", ".doc", ".docx",
    ".xls", ".xlsx", ".ppt", ".pptx",
}

_A_HREF_RE = re.compile(r"<(?:a|area)\b[^>]*?\bhref\s*=\s*[\"']([^\"']+)[\"']", re.I)
_SCRIPT_SRC_RE = re.compile(r"<script\b[^>]*?\bsrc\s*=\s*[\"']([^\"']+)[\"']", re.I)
_IMG_SRC_RE = re.compile(r"<img\b[^>]*?\bsrc\s*=\s*[\"']([^\"']+)[\"']", re.I)
_LINK_TAG_RE = re.compile(r"<link\b[^>]*>", re.I)
_ATTR_RE = re.compile(r"([a-zA-Z_:][-a-zA-Z0-9_:.]*)\s*=\s*[\"']([^\"']*)[\"']")
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)

ProgressCallback = Callable[[str], Awaitable[None]]


@dataclass
class CrawlResult:
    """Files fetched from a website, keyed by repository-style paths."""

    origin: str
    start_url: str
    files: dict[str, str] = field(default_factory=dict)
    title: str | None = None
    fetched: int = 0
    skipped: int = 0
    bytes: int = 0
    truncated: bool = False
    notes: list[str] = field(default_factory=list)


def normalize_url(raw: str, base: str | None = None) -> str | None:
    """Absolute http(s) URL with fragment and query removed (stable paths)."""
    candidate = urljoin(base, raw.strip()) if base else raw.strip()
    if not candidate:
        return None
    if candidate.startswith("//"):
        candidate = "https:" + candidate
    cleaned, _fragment = urldefrag(candidate)
    parsed = urlparse(cleaned)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return None
    return parsed._replace(query="", fragment="").geturl()


def path_for(url: str, content_type: str) -> str:
    """Map a fetched URL onto a repo-style path (`/` -> `index.html`)."""
    parsed = urlparse(url)
    path = (parsed.path or "/").lstrip("/")
    name = path.rstrip("/").split("/")[-1] if path else ""
    if parsed.path.endswith("/") or not name:
        path = f"{path.rstrip('/')}/index.html" if path else "index.html"
    elif "." not in name:
        if content_type in HTML_CONTENT_TYPES:
            path = f"{path}/index.html"
        else:
            path = path + _EXT_FOR_TYPE.get(content_type, ".txt")
    return path or "index.html"


def extract_links(html: str, base: str) -> list[str]:
    """Page links plus linked stylesheets, scripts and SVG images."""
    found: list[str] = []

    def add(raw: str) -> None:
        raw = (raw or "").strip()
        if not raw or raw.startswith(("#", "mailto:", "tel:", "javascript:", "data:", "blob:")):
            return
        absolute = urljoin(base, raw)
        if urlparse(absolute).scheme in ("http", "https"):
            found.append(absolute)

    for match in _A_HREF_RE.finditer(html):
        add(match.group(1))
    for match in _SCRIPT_SRC_RE.finditer(html):
        add(match.group(1))
    for match in _IMG_SRC_RE.finditer(html):
        add(match.group(1))
    for tag in _LINK_TAG_RE.finditer(html):
        attrs = dict(_ATTR_RE.findall(tag.group(0)))
        href = attrs.get("href")
        if not href:
            continue
        rel = (attrs.get("rel") or "").lower()
        if "stylesheet" in rel or (attrs.get("as") or "").lower() == "style":
            add(href)
    return found


def _skip_url(url: str) -> bool:
    path = urlparse(url).path.lower()
    return any(path.endswith(suffix) for suffix in _SKIP_SUFFIXES)


class SiteCrawler:
    """Read-only snapshot of a public website for indexing.

    Same-origin only, bounded by page / byte / depth limits, and never
    requests blocked paths (`.env`, keys, `wp-config.php`, ...).
    """

    def __init__(
        self,
        *,
        max_pages: int = DEFAULT_MAX_PAGES,
        max_bytes: int = DEFAULT_MAX_BYTES,
        max_depth: int = DEFAULT_MAX_DEPTH,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        user_agent: str = USER_AGENT,
        settings: Settings | None = None,
    ):
        self.settings = settings or get_settings()
        self.max_pages = max(1, max_pages)
        self.max_bytes = max(64_000, max_bytes)
        self.max_depth = max(0, max_depth)
        self.timeout = timeout
        self.user_agent = user_agent

    async def crawl(
        self,
        url: str,
        *,
        progress: ProgressCallback | None = None,
    ) -> CrawlResult:
        start = normalize_url(url)
        if start is None:
            raise ValueError(f"Not a crawlable http(s) URL: {url!r}")
        parsed_start = urlparse(start)
        origin = f"{parsed_start.scheme}://{parsed_start.netloc}"

        result = CrawlResult(origin=origin, start_url=start)
        queue: deque[tuple[str, int]] = deque([(start, 0)])
        seen: set[str] = set()
        headers = {"User-Agent": self.user_agent, "Accept": "*/*"}

        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=self.timeout,
            headers=headers,
        ) as client:
            while queue:
                if len(result.files) >= self.max_pages:
                    result.truncated = True
                    break
                if result.bytes >= self.max_bytes:
                    result.truncated = True
                    break

                current, depth = queue.popleft()
                if current in seen:
                    continue
                seen.add(current)

                try:
                    response = await client.get(current)
                except httpx.HTTPError as exc:
                    result.skipped += 1
                    logger.debug("Skipping %s (%s)", current, exc)
                    continue

                final_url = normalize_url(str(response.url)) or current
                if urlparse(final_url).netloc != parsed_start.netloc:
                    result.skipped += 1  # redirected off the origin
                    continue
                if response.status_code >= 400:
                    result.skipped += 1
                    continue

                content_type = (
                    response.headers.get("content-type", "").split(";")[0].strip().lower()
                )
                if content_type not in TEXT_CONTENT_TYPES:
                    result.skipped += 1
                    continue

                raw = response.content
                if len(raw) > self.settings.max_file_bytes:
                    result.skipped += 1
                    continue
                if result.bytes + len(raw) > self.max_bytes:
                    result.truncated = True
                    break

                path = path_for(final_url, content_type)
                if is_blocked_path(path) or path in result.files:
                    if is_blocked_path(path):
                        result.skipped += 1
                    continue

                text = raw.decode("utf-8", errors="replace")
                result.files[path] = text
                result.bytes += len(raw)
                result.fetched += 1

                if progress:
                    await progress(f"Crawled {result.fetched}/{self.max_pages} — {path}")

                if content_type in HTML_CONTENT_TYPES:
                    if result.title is None:
                        title_match = _TITLE_RE.search(text)
                        if title_match:
                            result.title = title_match.group(1).strip()[:200]
                    if depth < self.max_depth:
                        for link in extract_links(text, final_url):
                            normalized = normalize_url(link)
                            if normalized is None or normalized in seen:
                                continue
                            if urlparse(normalized).netloc != parsed_start.netloc:
                                continue
                            if _skip_url(normalized):
                                continue
                            # `is_blocked_path` expects a repo-relative path.
                            url_path = urlparse(normalized).path.lstrip("/")
                            if url_path and is_blocked_path(url_path):
                                continue
                            queue.append((normalized, depth + 1))

        if not result.files:
            result.notes.append("No indexable files could be fetched from this URL.")
        if result.truncated:
            result.notes.append(
                f"Crawl stopped at the configured limit ({self.max_pages} pages / "
                f"{self.max_bytes} bytes); more pages may exist."
            )
        result.notes.append(
            "Website snapshot: only files the server sends to browsers were "
            "fetched - server-side source (e.g. PHP) is not accessible."
        )
        return result


def build_scan_result(
    owner: str,
    repo: str,
    ref: str,
    crawl: CrawlResult,
    *,
    settings: Settings | None = None,
) -> ScanResult:
    """Turn crawled files into the same ScanResult the GitHub path produces."""
    settings = settings or get_settings()
    result = ScanResult(owner=owner, repo=repo, ref=ref)
    classified_meta: dict[str, tuple[str | None, str | None, bool]] = {}

    for path in sorted(crawl.files):
        size = len(crawl.files[path].encode("utf-8", errors="ignore"))
        classification = classify(path, size)
        result.all_paths.append(path)
        classified_meta[path] = (
            classification.language,
            classification.category,
            classification.is_wordpress_file,
        )
        result.counts[classification.category] = (
            result.counts.get(classification.category, 0) + 1
        )
        if size > settings.max_file_bytes:
            result.too_large += 1
            continue
        if not classification.is_source:
            continue
        result.files.append(ClassifiedFile(**classification.model_dump()))

    result.total_entries = len(result.all_paths)
    result.files.sort(key=lambda f: f.path)
    result.tree, result.tree_truncated = build_tree(
        result.all_paths,
        max_nodes=settings.max_tree_nodes,
        classify_meta=classified_meta,
    )
    result.notes.extend(crawl.notes)
    if not result.files:
        result.notes.append("No scannable files were found at this URL.")
    return result
