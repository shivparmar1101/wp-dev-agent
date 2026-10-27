from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable
from urllib.parse import urlparse

from backend.config import Settings, get_settings
from backend.github.client import GitHubClient, GitHubError
from backend.github.files import FileService
from backend.indexing.indexer import IndexRegistry, RepositoryIndexer, registry as default_registry
from backend.models.project import ProjectSummary, ScanStatus, StageStatus
from backend.scanner.project_detector import ProjectDetector
from backend.scanner.repository_scanner import RepositoryScanner, ScanResult
from backend.scanner.web_crawler import SiteCrawler, build_scan_result, normalize_url
from backend.scanner.web_store import save_site
from backend.storage.scans import ProjectStore, ScanStore, scan_status_from_row
from backend.utils.helpers import utcnow
from backend.utils.logging import get_logger

logger = get_logger(__name__)

ReadFn = Callable[[str], Awaitable[str | None]]

STAGES: list[tuple[str, str]] = [
    ("connecting", "Connecting to GitHub"),
    ("reading_tree", "Reading repository tree"),
    ("detecting_wordpress", "Detecting WordPress"),
    ("detecting_themes", "Detecting themes"),
    ("detecting_plugins", "Detecting plugins"),
    ("detecting_elementor", "Detecting Elementor"),
    ("indexing_php", "Indexing PHP"),
    ("indexing_css", "Indexing CSS"),
    ("indexing_javascript", "Indexing JavaScript"),
    ("building_index", "Building search index"),
]

_TECH_BY_CATEGORY = {
    "php": "php",
    "css": "css",
    "scss": "css",
    "javascript": "javascript",
    "typescript": "javascript",
    "html": "html",
    "json": "json",
    "yaml": "config",
    "configuration": "config",
    "markdown": "markdown",
}

#: Same stage ids (the UI keys off them) with labels that fit a website crawl.
WEB_STAGES: list[tuple[str, str]] = [
    ("connecting", "Fetching website"),
    ("reading_tree", "Crawling pages and assets"),
    ("detecting_wordpress", "Detecting WordPress"),
    ("detecting_themes", "Detecting themes"),
    ("detecting_plugins", "Detecting plugins"),
    ("detecting_elementor", "Detecting Elementor"),
    ("indexing_php", "Indexing HTML"),
    ("indexing_css", "Indexing CSS"),
    ("indexing_javascript", "Indexing JavaScript"),
    ("building_index", "Building search index"),
]

WEB_OWNER = "web"


def _stage_statuses(*, web: bool) -> list[StageStatus]:
    source = WEB_STAGES if web else STAGES
    return [StageStatus(id=stage_id, label=label) for stage_id, label in source]


class _StageTracker:
    """Stage progress bookkeeping shared by GitHub and website scans."""

    def __init__(
        self,
        scan_store: ScanStore,
        scan_id: str,
        branch: str | None,
        stages: list[StageStatus],
    ):
        self.scan_store = scan_store
        self.scan_id = scan_id
        self.branch = branch
        self.stages = stages
        self.by_id = {stage.id: stage for stage in stages}
        self.current_stage = stages[0].id if stages else ""

    def progress_ratio(self) -> float:
        done = sum(1 for stage in self.stages if stage.status in ("done", "skipped"))
        return round(done / len(self.stages), 4) if self.stages else 0.0

    def mark_running(self, stage_id: str, detail: str | None = None) -> None:
        self.current_stage = stage_id
        stage = self.by_id.get(stage_id)
        if stage is not None and stage.status != "done":
            stage.status = "running"
            if detail:
                stage.detail = detail
        self.save(status="running")

    def mark_done(self, stage_id: str, detail: str | None = None) -> None:
        stage = self.by_id.get(stage_id)
        if stage is not None:
            stage.status = "done"
            if detail:
                stage.detail = detail
        # Auto-start the next pending stage.
        for candidate in self.stages:
            if candidate.status == "pending":
                candidate.status = "running"
                break
        self.save(status="running")

    def save(self, **kwargs: Any) -> None:
        self.scan_store.update(
            self.scan_id,
            status=kwargs.pop("status", "running"),
            progress=kwargs.pop("progress", self.progress_ratio()),
            stages=self.stages,
            branch=self.branch,
            **kwargs,
        )

    def fail(self, message: str, detail: str | None) -> None:
        stage = self.by_id.get(self.current_stage)
        if stage is not None:
            stage.status = "error"
            stage.detail = message
        self.scan_store.update(
            self.scan_id,
            status="failed",
            stages=self.stages,
            error=message,
            error_details=detail if self.settings_debug else None,
            finished=True,
        )

    @property
    def settings_debug(self) -> bool:
        return bool(get_settings().debug)


class ScanJobRunner:
    """Runs repository scans as background tasks with real stage progress."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        scan_store: ScanStore | None = None,
        project_store: ProjectStore | None = None,
        registry: IndexRegistry | None = None,
        embeddings_enabled: bool = False,
    ):
        self.settings = settings or get_settings()
        self.scan_store = scan_store or ScanStore()
        self.project_store = project_store or ProjectStore()
        self.registry = registry or default_registry
        self.embeddings_enabled = embeddings_enabled
        self._tasks: dict[str, asyncio.Task] = {}
        self._running: dict[str, str] = {}  # "owner/repo" -> scan_id
        self._summaries: dict[str, ProjectSummary] = {}

    # -- public API --------------------------------------------------------
    def start(
        self,
        *,
        owner: str,
        repo: str,
        token: str,
        branch: str | None = None,
    ) -> ScanStatus:
        key = f"{owner.lower()}/{repo.lower()}"
        running_id = self._running.get(key)
        if running_id:
            status = self.get_status(running_id)
            if status is not None:
                return status

        scan_id = self.scan_store.create_scan(owner, repo)
        self._running[key] = scan_id
        task = asyncio.create_task(self._run(scan_id, owner, repo, token, branch))
        self._tasks[scan_id] = task

        def _cleanup(t: asyncio.Task, scan_id: str = scan_id, key: str = key) -> None:
            self._tasks.pop(scan_id, None)
            if self._running.get(key) == scan_id:
                self._running.pop(key, None)
            if t.cancelled():
                return
            exc = t.exception()
            if exc is not None:  # pragma: no cover - defensive
                logger.error("Scan task crashed: %s", exc)

        task.add_done_callback(_cleanup)
        status = self.get_status(scan_id)
        assert status is not None
        return status

    def get_status(self, scan_id: str) -> ScanStatus | None:
        row = self.scan_store.get(scan_id)
        if row is None:
            return None
        status = scan_status_from_row(row)
        if status.status == "completed":
            status.summary = self._summary_for(scan_id, status.owner, status.repo)
        return status

    def latest_status(self, owner: str, repo: str) -> ScanStatus | None:
        row = self.scan_store.latest_for(owner, repo)
        if row is None:
            return None
        return self.get_status(row["id"])

    def _summary_for(self, scan_id: str, owner: str, repo: str) -> ProjectSummary | None:
        if scan_id in self._summaries:
            return self._summaries[scan_id]
        summary = self.project_store.get(owner, repo)
        if summary is not None:
            index = self.registry.get_or_load(owner, repo)
            if index is not None:
                summary = summary.model_copy(update={"index": index.stats})
        return summary

    def is_running(self, owner: str, repo: str) -> bool:
        return f"{owner.lower()}/{repo.lower()}" in self._running

    # -- execution ---------------------------------------------------------
    async def _run(
        self,
        scan_id: str,
        owner: str,
        repo: str,
        token: str,
        branch: str | None,
    ) -> None:
        tracker = _StageTracker(self.scan_store, scan_id, branch, _stage_statuses())

        client = GitHubClient(
            token,
            api_url=self.settings.github_api_url,
            user_agent=self.settings.http_user_agent,
        )
        try:
            # 1. Connect
            tracker.mark_running("connecting", "Fetching repository metadata")
            meta = await client.get_repository(owner, repo)
            resolved_branch = branch or str(meta.get("default_branch") or "main")
            tracker.branch = resolved_branch
            tracker.mark_done("connecting", f"Connected (branch: {resolved_branch})")

            # 2. Read tree
            tracker.mark_running("reading_tree", "Fetching repository tree")
            scanner = RepositoryScanner(client, self.settings)

            async def tree_progress(stage_id: str, detail: str) -> None:
                stage = tracker.by_id.get(stage_id)
                if stage is not None:
                    stage.detail = detail
                tracker.save()

            scan = await scanner.scan(owner, repo, resolved_branch, progress=tree_progress)
            tracker.mark_done(
                "reading_tree",
                f"{len(scan.all_paths)} files, {scan.ignored_entries} ignored",
            )

            file_service = FileService(client, self.settings)

            async def read(path: str) -> str | None:
                return await file_service.read_text(owner, repo, path, resolved_branch)

            await self._analyze_and_index(
                scan_id=scan_id,
                tracker=tracker,
                owner=owner,
                repo=repo,
                ref=resolved_branch,
                description=meta.get("description"),
                scan=scan,
                read=read,
            )
        except GitHubError as exc:
            tracker.fail(exc.user_message(), exc.detail)
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Scan %s failed", scan_id[:8])
            message = "Repository analysis failed due to an unexpected error."
            if self.settings.debug:
                message = f"{message} ({exc})"
            tracker.fail(message, repr(exc))
        finally:
            await client.aclose()

    # -- website (URL) scans -------------------------------------------------
    def start_url(self, url: str) -> ScanStatus:
        """Crawl a public website and index every file it serves to browsers."""
        normalized = normalize_url(url)
        if normalized is None:
            raise ValueError("Enter a valid http:// or https:// website URL.")
        hostname = urlparse(normalized).netloc
        if not hostname:
            raise ValueError("Enter a valid http:// or https:// website URL.")

        owner, repo = WEB_OWNER, hostname
        key = f"{owner}/{repo}".lower()
        running_id = self._running.get(key)
        if running_id:
            status = self.get_status(running_id)
            if status is not None:
                return status

        scan_id = self.scan_store.create_scan(owner, repo)
        self._running[key] = scan_id
        task = asyncio.create_task(self._run_url(scan_id, normalized))
        self._tasks[scan_id] = task

        def _cleanup(t: asyncio.Task, scan_id: str = scan_id, key: str = key) -> None:
            self._tasks.pop(scan_id, None)
            if self._running.get(key) == scan_id:
                self._running.pop(key, None)
            if t.cancelled():
                return
            exc = t.exception()
            if exc is not None:  # pragma: no cover - defensive
                logger.error("Website scan task crashed: %s", exc)

        task.add_done_callback(_cleanup)
        status = self.get_status(scan_id)
        assert status is not None
        return status

    async def _run_url(self, scan_id: str, url: str) -> None:
        """Crawl a website, then reuse the normal analysis/index pipeline."""
        hostname = urlparse(url).netloc
        owner, repo, ref = WEB_OWNER, hostname, "site"
        repository = f"{owner}/{repo}"
        tracker = _StageTracker(
            self.scan_store, scan_id, ref, _stage_statuses(web=True)
        )
        tracker.save(status="running")

        try:
            tracker.mark_running("connecting", f"Fetching {url}")
            crawler = SiteCrawler(settings=self.settings)

            async def crawl_progress(note: str) -> None:
                tracker.mark_running("reading_tree", note)

            crawl = await crawler.crawl(url, progress=crawl_progress)
            scan = build_scan_result(owner, repo, ref, crawl)
            tracker.mark_done("connecting", f"Fetched {crawl.fetched} files")
            tracker.mark_done("reading_tree", f"{crawl.fetched} files crawled")

            contents = dict(crawl.files)

            async def read(path: str) -> str | None:
                return contents.get(path)

            await self._analyze_and_index(
                scan_id=scan_id,
                tracker=tracker,
                owner=owner,
                repo=repo,
                ref=ref,
                description=crawl.title or f"Website snapshot of {hostname}",
                scan=scan,
                read=read,
            )
            # Persist the snapshot so the file viewer and chat keep working
            # after a restart (GitHub-backed reads cannot serve these files).
            await asyncio.to_thread(save_site, hostname, contents)
            logger.info(
                "Website scan %s completed for %s (%d files, %d bytes)",
                scan_id[:8], repository, crawl.fetched, crawl.bytes,
            )
        except ValueError as exc:
            tracker.fail(str(exc), repr(exc))
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Website scan %s failed", scan_id[:8])
            message = "Website analysis failed due to an unexpected error."
            if self.settings.debug:
                message = f"{message} ({exc})"
            tracker.fail(message, repr(exc))

    # -- shared analysis path ------------------------------------------------
    async def _analyze_and_index(
        self,
        *,
        scan_id: str,
        tracker: _StageTracker,
        owner: str,
        repo: str,
        ref: str,
        description: str | None,
        scan: ScanResult,
        read: ReadFn,
    ) -> None:
        """Detect WordPress, index the files, and persist the project summary.

        Shared verbatim by GitHub repository scans and website (URL) scans.
        """
        from backend.wordpress.analyzer import WordPressAnalyzer

        analyzer = WordPressAnalyzer(read, self.settings)

        # 3. WordPress
        tracker.mark_running("detecting_wordpress")
        wordpress = await analyzer.detect_wordpress(scan)
        tracker.mark_done(
            "detecting_wordpress",
            f"confidence {wordpress.confidence:.2f}"
            + ("" if wordpress.is_wordpress else " (not detected)"),
        )

        # 4. Themes
        tracker.mark_running("detecting_themes")
        themes = await analyzer.detect_themes(scan)
        tracker.mark_done("detecting_themes", f"{len(themes)} theme(s) found")

        # 5. Plugins
        tracker.mark_running("detecting_plugins")
        plugins = await analyzer.detect_plugins(scan)
        tracker.mark_done("detecting_plugins", f"{len(plugins)} plugin(s) found")

        # 6. Elementor
        tracker.mark_running("detecting_elementor")
        elementor = await analyzer.detect_elementor(scan, wordpress)
        tracker.mark_done("detecting_elementor", f"Elementor: {elementor.elementor}")

        # 7-10. Indexing
        indexing_stages = (
            "indexing_php",
            "indexing_css",
            "indexing_javascript",
            "building_index",
        )
        for stage_id in indexing_stages:
            tracker.mark_running(stage_id)

        indexer = RepositoryIndexer(read, self.settings)

        async def index_progress(stage_id: str, detail: str) -> None:
            if stage_id in tracker.by_id:
                tracker.mark_done(stage_id, detail)

        index = await indexer.build(scan, progress=index_progress)
        index.stats.embeddings_enabled = self.embeddings_enabled
        for stage_id in indexing_stages:
            stage = tracker.by_id[stage_id]
            if stage.status != "done":
                stage.status = "done"
                if not stage.detail:
                    stage.detail = "Complete"

        self.registry.put(index)
        # Persist so search / file tree / chat keep working after a restart
        # or after the in-memory LRU entry is evicted.
        self.registry.save(index)

        # Summary
        detector = ProjectDetector()
        project_detection = detector.detect(scan, wordpress)
        tech: dict[str, bool] = {}
        for category, key in _TECH_BY_CATEGORY.items():
            if scan.counts.get(category):
                tech[key] = True

        notes = list(dict.fromkeys(scan.notes + analyzer_notes(index, project_detection.indicators)))
        summary = ProjectSummary(
            repository=f"{owner}/{repo}",
            owner=owner,
            repo=repo,
            branch=ref,
            description=description,
            project_types=project_detection.types,
            is_wordpress=wordpress.is_wordpress,
            wordpress_confidence=wordpress.confidence,
            wordpress_indicators=wordpress.indicators,
            elementor=elementor,
            themes=themes,
            plugins=plugins,
            file_counts=dict(sorted(scan.counts.items(), key=lambda kv: -kv[1])),
            total_files=len(scan.all_paths),
            source_files=len(scan.files),
            languages=sorted({f.language for f in scan.files if f.language}),
            tech=tech,
            index=index.stats,
            notes=notes,
            scanned_at=utcnow(),
        )
        self.project_store.upsert(summary)
        self._summaries[scan_id] = summary
        if len(self._summaries) > 20:
            self._summaries.pop(next(iter(self._summaries)))

        tracker.save(status="completed", progress=1.0, finished=True)
        logger.info(
            "Scan %s completed for %s/%s (%s chunks)",
            scan_id[:8], owner, repo, index.stats.chunks,
        )


def analyzer_notes(index, indicators: list[str]) -> list[str]:
    notes: list[str] = []
    if indicators:
        notes.extend(f"Project: {i}" for i in indicators[:4])
    if index.stats.files_indexed:
        notes.append(
            f"Indexed {index.stats.files_indexed} source files "
            f"({index.stats.chunks} chunks) for search."
        )
    return notes
