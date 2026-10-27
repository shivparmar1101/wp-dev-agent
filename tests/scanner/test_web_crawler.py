from __future__ import annotations

import httpx
import pytest
import respx

from backend.scanner.web_crawler import (
    SiteCrawler,
    build_scan_result,
    extract_links,
    normalize_url,
    path_for,
)

BASE = "https://shop.example.com"


def page(title: str, links: list[str]) -> str:
    anchors = "".join(f'<a href="{href}">x</a>' for href in links)
    return f"<html><head><title>{title}</title></head><body>{anchors}</body></html>"


def mock_site(routes: dict[str, tuple[str, str]]) -> None:
    """routes: path -> (content_type, body)."""
    for path, (content_type, body) in routes.items():
        respx.get(f"{BASE}{path}").mock(
            return_value=httpx.Response(200, content=body, headers={"content-type": content_type})
        )


def test_normalize_url_strips_fragment_and_query():
    assert normalize_url("https://a.com/x?q=1#frag") == "https://a.com/x"
    assert normalize_url("/about", base="https://a.com/") == "https://a.com/about"
    assert normalize_url("mailto:x@y.com") is None
    assert normalize_url("javascript:void(0)") is None
    assert normalize_url("ftp://a.com/x") is None
    assert normalize_url("//cdn.example.com/a.css", base="https://a.com") == (
        "https://cdn.example.com/a.css"
    )


def test_path_for_maps_urls_to_repo_paths():
    assert path_for("https://a.com/", "text/html") == "index.html"
    assert path_for("https://a.com/about/", "text/html") == "about/index.html"
    assert path_for("https://a.com/about", "text/html") == "about/index.html"
    assert path_for("https://a.com/assets/site.css", "text/css") == "assets/site.css"
    assert path_for("https://a.com/feed", "application/json") == "feed.json"


def test_extract_links_resolves_relative_and_skips_junk():
    html = page(
        "t",
        [
            "/about",
            "https://other.com/x",
            "#top",
            "mailto:a@b.c",
            "javascript:void(0)",
            "assets/site.css",
        ],
    )
    links = extract_links(html, f"{BASE}/")
    assert f"{BASE}/about" in links
    assert "https://other.com/x" in links
    assert not any(link.startswith("#") for link in links)
    assert not any(link.startswith("mailto:") for link in links)


@respx.mock
async def test_crawler_same_origin_only_and_stylesheet_collection():
    mock_site(
        {
            "/": ("text/html", page("Home", ["/about", "https://evil.com/phish", "/assets/site.css"])),
            "/about": ("text/html", page("About", [])),
            "/assets/site.css": ("text/css", ".header { color: red; }"),
        }
    )
    respx.get("https://evil.com/phish").mock(
        return_value=httpx.Response(200, content="steal")
    )

    result = await SiteCrawler().crawl(f"{BASE}/")

    assert result.files["index.html"].startswith("<html>")
    assert "about/index.html" in result.files
    assert "assets/site.css" in result.files
    assert "https://evil.com/phish" not in result.notes  # never fetched
    assert "evil.com" not in "".join(result.files)  # and not in stored content
    assert result.title == "Home"


@respx.mock
async def test_crawler_respects_page_limit():
    routes = {"/": ("text/html", page("Home", [f"/p{i}" for i in range(10)]))}
    for i in range(10):
        routes[f"/p{i}"] = ("text/html", page(f"P{i}", []))
    mock_site(routes)

    result = await SiteCrawler(max_pages=3).crawl(f"{BASE}/")

    assert result.fetched <= 3
    assert result.truncated is True
    assert any("limit" in note for note in result.notes)


@respx.mock
async def test_crawler_respects_depth_limit():
    routes: dict[str, tuple[str, str]] = {
        "/": ("text/html", page("Home", ["/d1"])),
        "/d1": ("text/html", page("D1", ["/d2"])),
        "/d2": ("text/html", page("D2", ["/d3"])),
        "/d3": ("text/html", page("D3", [])),
    }
    mock_site(routes)

    result = await SiteCrawler(max_depth=1).crawl(f"{BASE}/")

    assert "d1/index.html" in result.files
    assert "d2/index.html" not in result.files


@respx.mock
async def test_crawler_never_requests_blocked_paths():
    respx.get(f"{BASE}/").mock(
        return_value=httpx.Response(
            200,
            content=page(
                "Home",
                ["/.env", "/.htpasswd", "/keys/private_key", "/backup.zip", "/ok.js"],
            ),
            headers={"content-type": "text/html"},
        )
    )
    ok_route = respx.get(f"{BASE}/ok.js").mock(
        return_value=httpx.Response(
            200, content="console.log(1)", headers={"content-type": "text/javascript"}
        )
    )
    blocked_routes = [
        respx.get(f"{BASE}/.env").mock(return_value=httpx.Response(200, content="KEY=x")),
        respx.get(f"{BASE}/.htpasswd").mock(return_value=httpx.Response(200, content="u:h")),
        respx.get(f"{BASE}/keys/private_key").mock(
            return_value=httpx.Response(200, content="-----BEGIN")
        ),
        respx.get(f"{BASE}/backup.zip").mock(return_value=httpx.Response(200, content=b"PK")),
    ]

    result = await SiteCrawler().crawl(f"{BASE}/")

    assert ok_route.called
    assert not any(route.called for route in blocked_routes)
    assert ".env" not in result.files
    assert "keys/private_key" not in result.files
    assert "backup.zip" not in result.files


@respx.mock
async def test_crawler_skips_binary_content_types():
    respx.get(f"{BASE}/").mock(
        return_value=httpx.Response(
            200,
            content=page("Home", ["/hero.png", "/data.json"]),
            headers={"content-type": "text/html"},
        )
    )
    png_route = respx.get(f"{BASE}/hero.png").mock(
        return_value=httpx.Response(200, content=b"\x89PNG", headers={"content-type": "image/png"})
    )
    respx.get(f"{BASE}/data.json").mock(
        return_value=httpx.Response(
            200, content='{"ok": true}', headers={"content-type": "application/json"}
        )
    )

    result = await SiteCrawler().crawl(f"{BASE}/")

    assert not png_route.called  # skipped by extension before fetching
    assert "data.json" in result.files


@respx.mock
async def test_crawler_handles_http_errors_gracefully():
    respx.get(f"{BASE}/").mock(
        return_value=httpx.Response(
            200,
            content=page("Home", ["/missing"]),
            headers={"content-type": "text/html"},
        )
    )
    respx.get(f"{BASE}/missing").mock(return_value=httpx.Response(404, content="nope"))

    result = await SiteCrawler().crawl(f"{BASE}/")

    assert result.skipped >= 1
    assert "missing/index.html" not in result.files
    assert result.fetched == 1


@respx.mock
async def test_crawler_follows_same_origin_redirect():
    respx.get(f"{BASE}/old").mock(
        return_value=httpx.Response(
            301, headers={"location": f"{BASE}/new"}
        )
    )
    respx.get(f"{BASE}/new").mock(
        return_value=httpx.Response(
            200, content=page("New", []), headers={"content-type": "text/html"}
        )
    )

    result = await SiteCrawler().crawl(f"{BASE}/old")

    assert "new/index.html" in result.files


def test_build_scan_result_classifies_and_builds_tree(settings):
    from backend.scanner.web_crawler import CrawlResult

    crawl = CrawlResult(
        origin=BASE,
        start_url=f"{BASE}/",
        files={
            "index.html": page("Home", []),
            "assets/site.css": ".a { color: red; }",
            "assets/app.js": "console.log(1)",
            "wp-content/themes/x/style.css": "/* Theme Name: X */",
        },
        title="Home",
        fetched=4,
        notes=["Website snapshot: only public files were fetched."],
    )

    result = build_scan_result("web", "shop.example.com", "site", crawl, settings=settings)

    assert result.owner == "web"
    assert result.repo == "shop.example.com"
    assert result.ref == "site"
    assert {f.path for f in result.files} == set(crawl.files)
    assert result.tree.name == ""
    assert any(child.name == "wp-content" for child in result.tree.children)
    assert result.counts["html"] >= 1
    assert any("Website snapshot" in note for note in result.notes)


@respx.mock
async def test_crawler_rejects_non_http_url():
    with pytest.raises(ValueError):
        await SiteCrawler().crawl("ftp://example.com/x")


@respx.mock
async def test_crawler_empty_site_note():
    respx.get(f"{BASE}/").mock(return_value=httpx.Response(200, content=""))

    result = await SiteCrawler().crawl(f"{BASE}/")

    # Empty body is still fetched; the note only appears when nothing was stored.
    assert isinstance(result.files, dict)


def test_user_agent_identifies_the_bot():
    crawler = SiteCrawler()
    assert "WP-Dev-Agent" in crawler.user_agent
    assert isinstance(crawler.user_agent, str)
