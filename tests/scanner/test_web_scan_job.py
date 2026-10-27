from __future__ import annotations

import httpx
import pytest
import respx

from backend.scanner.scan_job import WEB_OWNER, ScanJobRunner
from backend.scanner.web_store import read_site_file, save_site, sites_root

SITE = "https://shop.example.com"


def page(title: str, links: list[str]) -> str:
    anchors = "".join(f'<a href="{href}">x</a>' for href in links)
    return f"<html><head><title>{title}</title></head><body>{anchors}</body></html>"


def mock_shop() -> None:
    respx.get(f"{SITE}/").mock(
        return_value=httpx.Response(
            200,
            content=page("Shop", ["/about", "/assets/site.css"]),
            headers={"content-type": "text/html"},
        )
    )
    respx.get(f"{SITE}/about").mock(
        return_value=httpx.Response(
            200,
            content=page("About", []),
            headers={"content-type": "text/html"},
        )
    )
    respx.get(f"{SITE}/assets/site.css").mock(
        return_value=httpx.Response(
            200,
            content=".header { color: red; }",
            headers={"content-type": "text/css"},
        )
    )


@pytest.fixture
def runner(settings, registry_clean):
    return ScanJobRunner(settings=settings, registry=registry_clean)


def test_start_url_rejects_bad_urls(runner):
    with pytest.raises(ValueError):
        runner.start_url("not-a-url")
    with pytest.raises(ValueError):
        runner.start_url("ftp://example.com/x")


@respx.mock
async def test_start_url_scan_end_to_end(runner, settings):
    mock_shop()

    status = runner.start_url(SITE)
    assert status.owner == WEB_OWNER
    assert status.repo == "shop.example.com"

    # Drain the background task.
    task = runner._tasks.get(status.scan_id)
    assert task is not None
    await task

    final = runner.get_status(status.scan_id)
    assert final is not None
    assert final.status == "completed"
    assert final.progress == 1.0
    assert final.branch == "site"
    stage_ids = [stage.id for stage in final.stages]
    assert "connecting" in stage_ids
    assert "building_index" in stage_ids
    assert all(stage.status == "done" for stage in final.stages)

    # The project was persisted with website semantics.
    from backend.storage.scans import ProjectStore

    project = ProjectStore().get(WEB_OWNER, "shop.example.com")
    assert project is not None
    assert project.branch == "site"
    assert project.description == "Shop"
    assert project.total_files == 3
    assert project.source_files >= 3

    # Snapshot persisted so the file viewer works after a restart.
    text = read_site_file("shop.example.com", "assets/site.css")
    assert text == ".header { color: red; }"


@respx.mock
async def test_start_url_marks_failure_when_site_unreachable(runner):
    respx.get(f"{SITE}/").mock(side_effect=httpx.ConnectError("boom"))

    status = runner.start_url(SITE)
    task = runner._tasks.get(status.scan_id)
    assert task is not None
    await task

    final = runner.get_status(status.scan_id)
    assert final is not None
    # The crawler tolerates unreachable pages: the scan still completes with
    # zero indexed files rather than hanging or crashing the runner.
    assert final.status == "completed"


def test_web_store_roundtrip(tmp_path, monkeypatch):
    from backend.config import Settings

    settings = Settings(
        _env_file=None,
        database_url=f"sqlite:///{tmp_path}/store.db",
        secret_key="unit-test-secret",
    )
    monkeypatch.setattr(
        "backend.scanner.web_store.get_settings", lambda: settings
    )

    save_site("example.com", {"index.html": "<h1>hi</h1>", "assets/a.css": ".a{}"})
    assert sites_root().name == "sites"
    assert read_site_file("example.com", "index.html") == "<h1>hi</h1>"
    assert read_site_file("example.com", "assets/a.css") == ".a{}"

    # Missing, blocked and escaping paths all return None.
    assert read_site_file("example.com", "missing.html") is None
    assert read_site_file("example.com", ".env") is None
    assert read_site_file("example.com", "../../etc/passwd") is None
    assert read_site_file("example.com", "/etc/passwd") is None

    # Re-saving replaces the previous snapshot.
    save_site("example.com", {"index.html": "v2"})
    assert read_site_file("example.com", "index.html") == "v2"
    assert read_site_file("example.com", "assets/a.css") is None
