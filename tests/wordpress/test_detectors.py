from __future__ import annotations

from backend.models.project import WordPressDetection
from backend.wordpress.elementor_detector import ElementorDetector
from backend.wordpress.plugin_detector import PluginDetector
from backend.wordpress.theme_detector import ThemeDetector


def test_detects_child_theme(wp_scan, wp_files):
    detector = ThemeDetector()
    themes = detector.detect(
        paths=wp_scan.all_paths,
        dirs=wp_scan.dirs,
        contents={
            "wp-content/themes/custom-theme/style.css": wp_files[
                "wp-content/themes/custom-theme/style.css"
            ]
        },
    )
    assert len(themes) == 1
    theme = themes[0]
    assert theme.name == "Custom Theme"
    assert theme.theme_type == "child"
    assert theme.parent_theme == "astra"
    assert theme.version == "1.2.0"
    assert theme.location == "wp-content/themes/custom-theme/"
    assert theme.block_theme is True
    assert theme.has_functions_php is True


def test_detects_custom_theme_without_parent(scan_factory):
    files = {
        "wp-content/themes/acme/style.css": "/*\nTheme Name: Acme\nAuthor: Acme Ltd\n*/",
        "wp-content/themes/acme/functions.php": "<?php",
    }
    scan = scan_factory(files)
    detector = ThemeDetector()
    themes = detector.detect(paths=scan.all_paths, dirs=scan.dirs, contents=files)
    assert len(themes) == 1
    assert themes[0].theme_type == "custom"
    assert themes[0].parent_theme is None


def test_known_theme_is_recognized(scan_factory):
    files = {"wp-content/themes/astra/style.css": "/*\nTheme Name: Astra\n*/"}
    scan = scan_factory(files)
    detector = ThemeDetector()
    themes = detector.detect(paths=scan.all_paths, dirs=scan.dirs, contents=files)
    assert themes[0].theme_type == "known"


def test_no_themes_outside_wordpress():
    detector = ThemeDetector()
    assert detector.detect(paths=["src/style.css", "assets/main.css"], dirs=["src"]) == []


def test_root_style_css_with_theme_header_is_a_standalone_theme():
    """A theme repository keeps its style.css at the root."""
    detector = ThemeDetector()
    themes = detector.detect(
        paths=["style.css", "functions.php"],
        dirs=[],
        contents={"style.css": "/*\nTheme Name: Solo Theme\nVersion: 2.0\n*/"},
    )
    assert len(themes) == 1
    assert themes[0].name == "Solo Theme"
    assert themes[0].location == "./"


def test_root_style_css_without_theme_header_is_not_a_theme():
    """Plain HTML/CSS sites have a root stylesheet with no WP theme headers."""
    detector = ThemeDetector()
    themes = detector.detect(
        paths=["style.css", "index.html"],
        dirs=[],
        contents={"style.css": ":root { --brand: #111; }\nbody { margin: 0; }\n"},
    )
    assert themes == []


def test_detects_plugins_with_headers(wp_scan, wp_files):
    detector = PluginDetector()
    contents = {
        "wp-content/plugins/elementor/elementor.php": wp_files[
            "wp-content/plugins/elementor/elementor.php"
        ],
        "wp-content/plugins/contact-form-7/wp-contact-form-7.php": wp_files[
            "wp-content/plugins/contact-form-7/wp-contact-form-7.php"
        ],
    }
    plugins = detector.detect(paths=wp_scan.all_paths, dirs=wp_scan.dirs, contents=contents)
    by_slug = {p.slug: p for p in plugins}
    assert "elementor" in by_slug
    assert by_slug["elementor"].name == "Elementor"
    assert by_slug["elementor"].version == "3.25.0"
    assert by_slug["elementor"].known is True
    assert by_slug["elementor"].metadata_source == "plugin_header"
    assert by_slug["contact-form-7"].name == "Contact Form 7"


def test_directory_only_plugin_is_flagged_as_directory_metadata(wp_scan):
    detector = PluginDetector()
    plugins = detector.detect(paths=wp_scan.all_paths, dirs=wp_scan.dirs, contents={})
    custom = next(p for p in plugins if p.slug == "custom-snippets")
    assert custom.metadata_source == "directory"
    assert custom.name == "Custom Snippets"  # prettified slug, no invented metadata
    assert custom.version is None


def test_plugin_requires_php_files(scan_factory):
    files = {
        "wp-content/plugins/empty-plugin/readme.txt": "nothing here",
        "wp-content/plugins/real-plugin/real-plugin.php": "<?php /* Plugin Name: Real */",
    }
    scan = scan_factory(files)
    detector = PluginDetector()
    plugins = detector.detect(paths=scan.all_paths, dirs=scan.dirs, contents=files)
    assert [p.slug for p in plugins] == ["real-plugin"]


def test_elementor_detected_from_plugin_directory(wp_scan, wp_files):
    detector = ElementorDetector()
    result = detector.detect(
        paths=wp_scan.all_paths,
        dirs=wp_scan.dirs,
        contents={
            "wp-content/plugins/elementor/elementor.php": wp_files[
                "wp-content/plugins/elementor/elementor.php"
            ],
            "wp-content/plugins/elementor/assets/css/frontend.css": wp_files[
                "wp-content/plugins/elementor/assets/css/frontend.css"
            ],
        },
        wordpress=WordPressDetection(is_wordpress=True, confidence=0.9),
    )
    assert result.elementor == "detected"
    assert result.elementor_pro == "not_detected"
    assert any("plugin directory" in e.lower() for e in result.evidence)


def test_elementor_pro_detected(scan_factory):
    files = {"wp-content/plugins/elementor-pro/elementor-pro.php": "<?php"}
    scan = scan_factory(files)
    detector = ElementorDetector()
    result = detector.detect(
        paths=scan.all_paths,
        dirs=scan.dirs,
        contents={},
        wordpress=WordPressDetection(is_wordpress=True, confidence=0.9),
    )
    assert result.elementor == "detected"
    assert result.elementor_pro == "detected"


def test_elementor_detected_from_css_classes_only(scan_factory):
    files = {
        "theme/style.css": ".elementor-element-abc { color: red; }\n"
        ".elementor-widget { margin: 0; }"
    }
    scan = scan_factory(files)
    detector = ElementorDetector()
    result = detector.detect(
        paths=scan.all_paths,
        dirs=scan.dirs,
        contents=files,
        wordpress=WordPressDetection(is_wordpress=True, confidence=0.9),
    )
    assert result.elementor == "detected"
    assert any("CSS classes" in e for e in result.evidence)


def test_elementor_not_detected_on_plain_wordpress():
    detector = ElementorDetector()
    result = detector.detect(
        paths=["wp-config.php", "wp-content/themes/x/functions.php"],
        dirs=["wp-content", "wp-content/themes"],
        contents={},
        wordpress=WordPressDetection(is_wordpress=True, confidence=0.9),
    )
    assert result.elementor == "not_detected"
    assert result.elementor_pro == "not_detected"


def test_elementor_unknown_on_non_wordpress():
    detector = ElementorDetector()
    result = detector.detect(
        paths=["src/index.js"],
        dirs=["src"],
        contents={},
        wordpress=WordPressDetection(is_wordpress=False, confidence=0.1),
    )
    assert result.elementor == "unknown"
