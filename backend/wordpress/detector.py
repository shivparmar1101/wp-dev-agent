from __future__ import annotations

from backend.models.project import WordPressDetection
from backend.utils.logging import get_logger

logger = get_logger(__name__)

# path fragment / exact name -> (weight, indicator)
_DIR_SIGNALS: list[tuple[str, float, str]] = [
    ("wp-content", 0.30, "wp-content directory detected"),
    ("wp-admin", 0.30, "wp-admin directory detected"),
    ("wp-includes", 0.25, "wp-includes directory detected"),
]

_FILE_SIGNALS: list[tuple[str, float, str]] = [
    ("wp-config.php", 0.20, "wp-config.php detected"),
    ("wp-load.php", 0.15, "wp-load.php detected"),
    ("wp-blog-header.php", 0.10, "wp-blog-header.php detected"),
    ("wp-login.php", 0.08, "wp-login.php detected"),
    ("wp-cron.php", 0.05, "wp-cron.php detected"),
    ("xmlrpc.php", 0.05, "xmlrpc.php detected"),
    ("wp-settings.php", 0.08, "wp-settings.php detected"),
]

_STRUCTURE_SIGNALS: list[tuple[str, float, str]] = [
    ("/themes/", 0.12, "WordPress theme structure detected"),
    ("/plugins/", 0.06, "WordPress plugin directory structure detected"),
    ("wp-content/themes/", 0.12, "WordPress theme structure detected"),
    ("wp-content/plugins/", 0.06, "WordPress plugin directory structure detected"),
    ("wp-content/mu-plugins/", 0.04, "Must-use plugin directory detected"),
]

# PHP usage markers that are strongly associated with WordPress code.
_CONTENT_MARKERS = (
    "wp_head(",
    "wp_footer(",
    "add_action(",
    "add_filter(",
    "wp_enqueue_script(",
    "wp_enqueue_style(",
    "register_post_type(",
    "WP_Query",
    "get_header(",
    "get_footer(",
    "the_content(",
    "esc_html(",
    "esc_attr(",
    "wp_kses(",
    "is_active_sidebar(",
    "dynamic_sidebar(",
    "load_plugin_textdomain(",
)

_CONTENT_WEIGHT = 0.15
_CONTENT_MARKER_THRESHOLD = 3
_THRESHOLD = 0.5


class WordPressDetector:
    """Multi-signal WordPress detection.

    Signals are weighted and combined into a confidence score. A single weak
    signal (for example a stray `functions.php`) can never reach the
    detection threshold on its own.
    """

    def detect(
        self,
        *,
        paths: list[str] | None = None,
        dirs: list[str] | None = None,
        contents: dict[str, str] | None = None,
    ) -> WordPressDetection:
        paths = paths or []
        dirs = dirs or []
        contents = contents or {}

        signals: dict[str, float] = {}
        indicators: list[str] = []
        confidence = 0.0

        # 1. Core directories
        dir_set = {d.strip("/") for d in dirs}
        for fragment, weight, label in _DIR_SIGNALS:
            hit_dirs = [d for d in dir_set if d == fragment or d.endswith("/" + fragment)]
            if hit_dirs or any(
                p.startswith(fragment + "/") or "/" + fragment + "/" in "/" + p for p in paths
            ):
                if label not in signals:
                    signals[label] = weight
                if label not in indicators:
                    indicators.append(label)
                confidence += weight

        # 2. Core files
        path_set = set(paths)
        basenames = {p.rsplit("/", 1)[-1].lower() for p in paths}
        for name, weight, label in _FILE_SIGNALS:
            if name in basenames:
                if label not in signals:
                    signals[label] = weight
                indicators.append(label)
                confidence += weight

        # 3. Theme / plugin structures
        seen_structure: set[str] = set()
        for fragment, weight, label in _STRUCTURE_SIGNALS:
            if label in seen_structure:
                continue
            if any(fragment in p for p in paths):
                seen_structure.add(label)
                signals[label] = weight
                indicators.append(label)
                confidence += weight

        # 4. PHP usage markers in sampled content
        marker_hits: list[str] = []
        for path, text in contents.items():
            if not path.lower().endswith((".php", ".inc")):
                continue
            for marker in _CONTENT_MARKERS:
                if marker in text and marker not in marker_hits:
                    marker_hits.append(marker)
        if len(marker_hits) >= _CONTENT_MARKER_THRESHOLD:
            signals["WordPress PHP functions used in code"] = _CONTENT_WEIGHT
            indicators.append("WordPress PHP functions used in code")
            confidence += _CONTENT_WEIGHT

        # 5. readme.html mentioning WordPress
        for path, text in contents.items():
            if path.lower().endswith("readme.html") and "wordpress" in text.lower():
                signals["readme.html mentions WordPress"] = 0.05
                indicators.append("readme.html mentions WordPress")
                confidence += 0.05
                break

        confidence = round(min(1.0, confidence), 3)
        is_wordpress = confidence >= _THRESHOLD

        wp_content_paths: set[str] = set()
        for path in path_set:
            normalized = "/" + path.lstrip("/")
            if "/wp-content/" not in normalized:
                continue
            prefix = normalized.split("/wp-content/", 1)[0].lstrip("/")
            wp_content_paths.add(f"{prefix}/wp-content" if prefix else "wp-content")

        if not is_wordpress:
            indicators = [
                i for i in indicators
            ] or ["No strong WordPress signals found"]

        return WordPressDetection(
            is_wordpress=is_wordpress,
            confidence=confidence,
            indicators=indicators,
            signals=signals,
            content_markers=marker_hits[:8],
            wp_content_paths=sorted(wp_content_paths),
        )
