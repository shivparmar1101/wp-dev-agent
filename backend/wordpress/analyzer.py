from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from backend.config import Settings, get_settings
from backend.models.project import ElementorDetection, PluginInfo, ThemeInfo, WordPressDetection
from backend.scanner.repository_scanner import ScanResult
from backend.utils.logging import get_logger

from .detector import WordPressDetector
from .elementor_detector import ElementorDetector
from .plugin_detector import PluginDetector
from .theme_detector import ThemeDetector

logger = get_logger(__name__)

ReadFn = Callable[[str], Awaitable[str | None]]

_MAX_THEME_STYLES = 12
_MAX_PLUGIN_FILES = 30
_MAX_WP_SAMPLE_FILES = 12
_MAX_ELEMENTOR_FILES = 24


@dataclass
class WordPressAnalysis:
    wordpress: WordPressDetection
    themes: list[ThemeInfo] = field(default_factory=list)
    plugins: list[PluginInfo] = field(default_factory=list)
    elementor: ElementorDetection = field(default_factory=ElementorDetection)
    files_read: int = 0
    bytes_read: int = 0
    notes: list[str] = field(default_factory=list)


class WordPressAnalyzer:
    """Runs the individual detection stages against a scanned repository.

    File reads are cached and bounded by `scan_read_budget_bytes` so a huge
    repository cannot be pulled into memory.
    """

    def __init__(self, read: ReadFn, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self._read = read
        self._cache: dict[str, str | None] = {}
        self._bytes_read = 0
        self._lock = asyncio.Lock()

        self.detector = WordPressDetector()
        self.theme_detector = ThemeDetector()
        self.plugin_detector = PluginDetector()
        self.elementor_detector = ElementorDetector()

        self._wordpress: WordPressDetection | None = None
        self._themes: list[ThemeInfo] | None = None
        self._plugins: list[PluginInfo] | None = None
        self._elementor: ElementorDetection | None = None

    # -- helpers -----------------------------------------------------------
    async def _read_cached(self, path: str) -> str | None:
        if path in self._cache:
            return self._cache[path]
        if self._bytes_read >= self.settings.scan_read_budget_bytes:
            self._cache[path] = None
            return None
        try:
            text = await self._read(path)
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("Failed reading %s: %s", path, exc)
            text = None
        if text is None:
            self._cache[path] = None
            return None
        if len(text) > self.settings.max_index_file_bytes:
            text = text[: self.settings.max_index_file_bytes]
        self._bytes_read += len(text)
        self._cache[path] = text
        return text

    async def _read_many_cached(self, paths: list[str]) -> dict[str, str]:
        unique: list[str] = []
        for path in paths:
            if path not in unique:
                unique.append(path)
        results: dict[str, str] = {}
        # Small batches keep GitHub API usage predictable.
        for index in range(0, len(unique), 6):
            batch = unique[index : index + 6]
            values = await asyncio.gather(*(self._read_cached(p) for p in batch))
            for path, value in zip(batch, values):
                if value is not None:
                    results[path] = value
        return results

    @property
    def contents(self) -> dict[str, str]:
        return {k: v for k, v in self._cache.items() if v is not None}

    @property
    def files_read(self) -> int:
        return len([v for v in self._cache.values() if v is not None])

    @property
    def bytes_read(self) -> int:
        return self._bytes_read

    # -- stages ------------------------------------------------------------
    async def detect_wordpress(self, scan: ScanResult) -> WordPressDetection:
        if self._wordpress is not None:
            return self._wordpress

        candidates: list[str] = []
        root_names = {
            "wp-config.php",
            "wp-load.php",
            "wp-blog-header.php",
            "wp-settings.php",
            "wp-login.php",
            "wp-cron.php",
            "xmlrpc.php",
            "index.php",
            "readme.html",
            "license.txt",
        }
        for path in scan.all_paths:
            name = path.rsplit("/", 1)[-1].lower()
            depth = path.count("/")
            if name in root_names and depth <= 1:
                candidates.append(path)
            elif depth == 0 and name.endswith((".php", ".html")):
                candidates.append(path)
        # Sample theme functions.php and a few plugin bootstrap files.
        for path in scan.all_paths:
            if len(candidates) >= _MAX_WP_SAMPLE_FILES:
                break
            if path.endswith("/functions.php") or path.endswith("/wp-config.php"):
                candidates.append(path)

        contents = await self._read_many_cached(candidates[:_MAX_WP_SAMPLE_FILES])
        self._wordpress = self.detector.detect(
            paths=scan.all_paths, dirs=scan.dirs, contents=contents
        )
        return self._wordpress

    async def detect_themes(self, scan: ScanResult) -> list[ThemeInfo]:
        if self._themes is not None:
            return self._themes
        style_paths = [
            p
            for p in scan.all_paths
            if p.endswith("/style.css") or (p == "style.css")
        ]
        style_paths = style_paths[:_MAX_THEME_STYLES]
        contents = await self._read_many_cached(style_paths)
        self._themes = self.theme_detector.detect(
            paths=scan.all_paths, dirs=scan.dirs, contents=contents
        )
        return self._themes

    async def detect_plugins(self, scan: ScanResult) -> list[PluginInfo]:
        if self._plugins is not None:
            return self._plugins

        import re

        from .plugin_detector import _PLUGIN_DIR_RE, _MU_PLUGIN_RE

        candidates: list[str] = []
        seen_dirs: set[str] = set()
        for path in scan.all_paths:
            if "/" not in path:
                continue
            parent = path.rsplit("/", 1)[0]
            match = _PLUGIN_DIR_RE.search(parent)
            if not match:
                continue
            base = ((match.group("base") or "") + "plugins/" + match.group("slug")).rstrip("/")
            if base in seen_dirs:
                continue
            seen_dirs.add(base)
            slug = match.group("slug")
            preferred = f"{base}/{slug}.php"
            if preferred in scan.all_paths:
                candidates.append(preferred)
            else:
                root_php = sorted(
                    (
                        p
                        for p in scan.all_paths
                        if p.startswith(base + "/") and p.count("/") == base.count("/") + 1
                        and p.lower().endswith(".php")
                    ),
                    key=len,
                )
                if root_php:
                    candidates.append(root_php[0])
        for path in scan.all_paths:
            if _MU_PLUGIN_RE.search(path) and len(candidates) < _MAX_PLUGIN_FILES:
                candidates.append(path)

        contents = await self._read_many_cached(candidates[:_MAX_PLUGIN_FILES])
        self._plugins = self.plugin_detector.detect(
            paths=scan.all_paths, dirs=scan.dirs, contents=self.contents
        )
        # Plugin headers may only exist in files we just read.
        if contents:
            refreshed = self.plugin_detector.detect(
                paths=scan.all_paths, dirs=scan.dirs, contents=self.contents
            )
            self._plugins = refreshed
        return self._plugins

    async def detect_elementor(
        self, scan: ScanResult, wordpress: WordPressDetection | None = None
    ) -> ElementorDetection:
        if self._elementor is not None:
            return self._elementor
        wordpress = wordpress or await self.detect_wordpress(scan)

        candidates: list[str] = []
        interesting_ext = (".css", ".scss", ".less", ".php", ".js", ".html", ".twig")
        for path in scan.all_paths:
            lowered = path.lower()
            if len(candidates) >= _MAX_ELEMENTOR_FILES:
                break
            if "elementor" in lowered:
                candidates.append(path)
            elif lowered.endswith(interesting_ext) and any(
                key in lowered
                for key in (
                    "functions.php",
                    "header.php",
                    "footer.php",
                    "front-page.php",
                    "single.php",
                    "page.php",
                    "index.php",
                    "style.css",
                    "responsive",
                    "main.css",
                    "theme.js",
                )
            ):
                candidates.append(path)

        await self._read_many_cached(candidates[:_MAX_ELEMENTOR_FILES])
        self._elementor = self.elementor_detector.detect(
            paths=scan.all_paths,
            dirs=scan.dirs,
            contents=self.contents,
            wordpress=wordpress,
        )
        return self._elementor

    async def analyze(self, scan: ScanResult) -> WordPressAnalysis:
        wordpress = await self.detect_wordpress(scan)
        themes = await self.detect_themes(scan)
        plugins = await self.detect_plugins(scan)
        elementor = await self.detect_elementor(scan, wordpress)

        notes: list[str] = []
        if self._bytes_read >= self.settings.scan_read_budget_bytes:
            notes.append(
                "Detection used a bounded sample of files to keep the scan fast."
            )
        return WordPressAnalysis(
            wordpress=wordpress,
            themes=themes,
            plugins=plugins,
            elementor=elementor,
            files_read=self.files_read,
            bytes_read=self._bytes_read,
            notes=notes,
        )
