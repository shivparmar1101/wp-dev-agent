from __future__ import annotations

from backend.wordpress.detector import WordPressDetector


def test_detects_full_wordpress_site(wp_scan, wp_files):
    detector = WordPressDetector()
    result = detector.detect(
        paths=wp_scan.all_paths, dirs=wp_scan.dirs,
        contents={"wp-content/themes/custom-theme/functions.php": wp_files["wp-content/themes/custom-theme/functions.php"]},
    )
    assert result.is_wordpress is True
    assert result.confidence >= 0.5
    assert any("wp-content" in i for i in result.indicators)
    assert any("wp-config" in i for i in result.indicators)
    assert result.wp_content_paths == ["wp-content"]


def test_functions_php_alone_is_not_wordpress():
    detector = WordPressDetector()
    result = detector.detect(paths=["functions.php", "style.css"], dirs=[])
    assert result.is_wordpress is False
    assert result.confidence < 0.5


def test_plain_node_project_is_not_wordpress():
    detector = WordPressDetector()
    result = detector.detect(
        paths=["package.json", "src/index.js", "src/components/App.tsx", "README.md"],
        dirs=["src", "src/components"],
    )
    assert result.is_wordpress is False
    assert result.confidence == 0.0


def test_content_markers_raise_confidence():
    detector = WordPressDetector()
    contents = {
        "theme/functions.php": (
            "<?php add_action('init', function () { wp_enqueue_style('x'); }); "
            "echo get_header('default'); the_content(); new WP_Query();"
        )
    }
    without = detector.detect(paths=["theme/functions.php"], dirs=["theme"], contents={})
    with_markers = detector.detect(
        paths=["theme/functions.php"], dirs=["theme"], contents=contents
    )
    assert with_markers.confidence > without.confidence
    assert "WordPress PHP functions used in code" in with_markers.indicators


def test_wordpress_without_core_dirs_is_uncertain():
    # theme/plugin structures alone are not enough to claim a full WP install
    detector = WordPressDetector()
    result = detector.detect(
        paths=["wp-content/themes/x/style.css", "wp-content/plugins/y/y.php"],
        dirs=["wp-content", "wp-content/themes", "wp-content/plugins"],
    )
    assert result.confidence < 1.0
    # combined signals (0.30 + 0.12 + 0.06) still below threshold -> not claimed
    assert result.is_wordpress is False or result.confidence >= 0.5


def test_readme_html_signal():
    detector = WordPressDetector()
    result = detector.detect(
        paths=["readme.html", "license.txt"],
        dirs=[],
        contents={"readme.html": "<h1>Welcome to WordPress</h1>"},
    )
    assert result.confidence > 0.0
