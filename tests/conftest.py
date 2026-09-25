from __future__ import annotations

import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.config import Settings  # noqa: E402
from backend.models.file import ClassifiedFile  # noqa: E402
from backend.scanner.file_classifier import classify  # noqa: E402
from backend.scanner.repository_scanner import ScanResult, build_tree  # noqa: E402

WP_FILES: dict[str, str] = {
    "wp-config.php": "<?php\ndefine('DB_NAME', 'site');\ndefine('DB_PASSWORD', 'hunter2secret');\n",
    "index.php": "<?php get_header(); ?>\n",
    "readme.html": "<html><body><h1>Welcome to WordPress</h1></body></html>",
    "wp-content/themes/custom-theme/style.css": (
        "/*\nTheme Name: Custom Theme\nTemplate: astra\nAuthor: Acme\n"
        "Version: 1.2.0\nText Domain: custom-theme\n*/\n\n.header { width: 100%; }\n"
    ),
    "wp-content/themes/custom-theme/theme.json": '{"version": 2}',
    "wp-content/themes/custom-theme/functions.php": (
        "<?php\nfunction custom_setup() {\n  add_action('init', 'custom_setup');\n  "
        "wp_enqueue_style('custom', get_stylesheet_uri());\n}\n"
    ),
    "wp-content/themes/custom-theme/header.php": (
        "<!doctype html><html><?php wp_head(); ?><body><?php get_template_part('parts/nav'); ?></body></html>"
    ),
    "wp-content/themes/custom-theme/footer.php": "<?php wp_footer(); ?>",
    "wp-content/themes/custom-theme/assets/css/responsive.css": (
        ".header-container {\n  width: 1200px;\n}\n\n"
        "@media (max-width: 768px) {\n  .header-container {\n    overflow: hidden;\n  }\n}\n"
    ),
    "wp-content/themes/custom-theme/assets/js/nav.js": (
        "document.addEventListener('DOMContentLoaded', () => {\n"
        "  const toggle = document.querySelector('.menu-toggle');\n"
        "  toggle.addEventListener('click', () => document.body.classList.toggle('nav-open'));\n"
        "});\n"
    ),
    "wp-content/plugins/elementor/elementor.php": (
        "<?php\n/* Plugin Name: Elementor\nVersion: 3.25.0\nAuthor: Elementor.com\n*/\n"
        "$widget = \\Elementor\\Widget_Base;\n"
    ),
    "wp-content/plugins/elementor/assets/css/frontend.css": (
        ".elementor-element.elementor-element-abc { display: flex; }\n"
        ".elementor-widget-heading { margin: 0; }\n"
    ),
    "wp-content/plugins/contact-form-7/wp-contact-form-7.php": (
        "<?php\n/* Plugin Name: Contact Form 7\nVersion: 5.9.8\nAuthor: Takayoshi Miyake\n*/\n"
    ),
    "wp-content/plugins/custom-snippets/custom-snippets.php": "<?php // no header here\n",
    "assets/css/site.css": "body { margin: 0; }\n",
    "package.json": '{"name": "client-wordpress-site", "version": "1.0.0"}\n',
}


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        _env_file=None,
        database_url=f"sqlite:///{tmp_path}/test.db",
        secret_key="unit-test-secret",
        rate_limit_enabled=False,
        ai_provider="mock",
        ai_api_key="",
    )


@pytest.fixture
def wp_files() -> dict[str, str]:
    return dict(WP_FILES)


def make_scan(
    files: dict[str, str],
    *,
    owner: str = "acme",
    repo: str = "client-wordpress-site",
    ref: str = "main",
) -> ScanResult:
    scan = ScanResult(owner=owner, repo=repo, ref=ref)
    for path, content in files.items():
        classification = classify(path, len(content))
        scan.all_paths.append(path)
        scan.files.append(ClassifiedFile(**classification.model_dump()))
        parts = path.split("/")
        for index in range(1, len(parts)):
            directory = "/".join(parts[:index])
            if directory not in scan.dirs:
                scan.dirs.append(directory)
        scan.counts[classification.category] = scan.counts.get(classification.category, 0) + 1
    scan.files.sort(key=lambda f: f.path)
    scan.tree, _ = build_tree(scan.all_paths)
    return scan


@pytest.fixture
def wp_scan(wp_files) -> ScanResult:
    return make_scan(wp_files)


@pytest.fixture
def scan_factory():
    """Fixture wrapper around `make_scan` for ad-hoc repositories."""
    return make_scan


@pytest.fixture
def registry_clean():
    from backend.indexing.indexer import registry

    registry.clear()
    yield registry
    registry.clear()


class DictFileReader:
    """Async reader over a fixed file map - used as a GitHub stand-in."""

    def __init__(self, files: dict[str, str]):
        self.files = files
        self.calls: list[str] = []

    async def read(self, path: str) -> str | None:
        self.calls.append(path)
        return self.files.get(path)


@pytest.fixture
def dict_reader(wp_files) -> DictFileReader:
    return DictFileReader(dict(wp_files))
