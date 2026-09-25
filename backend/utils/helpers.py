from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Iterable, Iterator, Sequence, TypeVar

T = TypeVar("T")

_WORDPRESS_HEADER_KEYS = {
    "plugin name",
    "plugin uri",
    "description",
    "version",
    "author",
    "author uri",
    "text domain",
    "domain path",
    "license",
    "requires at least",
    "requires php",
    "network",
    "update uri",
    "theme name",
    "theme uri",
    "template",
    "tags",
    "status",
}

_KNOWN_SLUG_NAMES = {
    "elementor": "Elementor",
    "elementor-pro": "Elementor Pro",
    "contact-form-7": "Contact Form 7",
    "wp-mail-smtp": "WP Mail SMTP",
    "woocommerce": "WooCommerce",
    "wordpress-seo": "Yoast SEO",
    "wp-seo": "Yoast SEO",
    "wordfence": "Wordfence",
    "classic-editor": "Classic Editor",
    "jetpack": "Jetpack",
    "wpforms-lite": "WPForms Lite",
    "ninja-forms": "Ninja Forms",
    "advanced-custom-fields": "Advanced Custom Fields",
    "acf": "Advanced Custom Fields",
    "duplicate-post": "Duplicate Post",
    "w3-total-cache": "W3 Total Cache",
    "wp-super-cache": "WP Super Cache",
    "autoptimize": "Autoptimize",
    "really-simple-ssl": "Really Simple SSL",
    "redirection": "Redirection",
    "updraftplus": "UpdraftPlus",
    "litespeed-cache": "LiteSpeed Cache",
    "query-monitor": "Query Monitor",
    "revision-control": "Revision Control",
    "astra": "Astra",
    "hello-elementor": "Hello Elementor",
    "genesis": "Genesis",
    "generatepress": "GeneratePress",
    "kadence": "Kadence",
    "oceanwp": "OceanWP",
    "neve": "Neve",
    "storefront": "Storefront",
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime | None = None) -> str:
    value = dt or utcnow()
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def human_size(num_bytes: int | None) -> str:
    if not num_bytes:
        return "0 B"
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def prettify_slug(slug: str) -> str:
    if slug in _KNOWN_SLUG_NAMES:
        return _KNOWN_SLUG_NAMES[slug]
    words = re.split(r"[-_]+", slug.strip())
    return " ".join(w.capitalize() for w in words if w) or slug


def parse_wp_headers(content: str, keys: Iterable[str] | None = None) -> dict[str, str]:
    """Parse WordPress style `Field: Value` headers from the top of a file.

    Mirrors WordPress' `get_file_data()` behaviour closely enough for
    plugin/theme metadata detection: only the first 8 KB is inspected and only
    single line `Key: Value` pairs are considered.
    """
    if not content:
        return {}
    wanted = {k.lower() for k in keys} if keys is not None else _WORDPRESS_HEADER_KEYS
    headers: dict[str, str] = {}
    window = content[:8192]
    for raw_line in window.splitlines():
        line = raw_line.strip()
        if not line or len(line) > 300:
            continue
        if line in ("*/", "?>", "# */"):
            break
        cleaned = line.lstrip("/*#@ \t").strip()
        if ":" not in cleaned:
            continue
        key, _, value = cleaned.partition(":")
        key = key.strip().lower()
        value = value.strip()
        if key in wanted and value:
            headers[key] = value
    return headers


def chunked(seq: Sequence[T], size: int) -> Iterator[Sequence[T]]:
    for index in range(0, len(seq), size):
        yield seq[index : index + size]


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def tokenize_identifiers(text: str) -> list[str]:
    """Split camelCase / snake_case / kebab-case identifiers into words."""
    if not text:
        return []
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    spaced = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", spaced)
    parts = re.split(r"[^0-9A-Za-z]+", spaced)
    return [p.lower() for p in parts if p]


def ensure_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
