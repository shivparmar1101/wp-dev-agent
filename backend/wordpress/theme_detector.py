from __future__ import annotations

import re

from backend.models.project import ThemeInfo
from backend.utils.helpers import parse_wp_headers, prettify_slug

_THEME_KEYS = (
    "theme name",
    "theme uri",
    "author",
    "author uri",
    "description",
    "version",
    "template",
    "text domain",
    "domain path",
    "requires at least",
    "requires php",
    "license",
    "tags",
    "status",
    "updated",
)

_KNOWN_THEMES = {
    "astra",
    "oceanwp",
    "neve",
    "generatepress",
    "kadence",
    "hello-elementor",
    "genesis",
    "storefront",
    "divi",
    "avada",
    "blocksy",
    "twentytwentyone",
    "twentytwentytwo",
    "twentytwentythree",
    "twentytwentyfour",
    "twentytwentyfive",
}

_WILDCARD_PREFIXES = ("twentytwenty",)

_THEME_PATH_RE = re.compile(r"(?:^|/)(?P<base>.*/)?themes/(?P<slug>[^/]+)$")


def _known(slug: str) -> bool:
    lowered = slug.lower()
    if lowered in _KNOWN_THEMES:
        return True
    return any(lowered.startswith(prefix) for prefix in _WILDCARD_PREFIXES)


class ThemeDetector:
    """Identifies WordPress themes from `wp-content/themes/<slug>/style.css`."""

    def detect(
        self,
        *,
        paths: list[str],
        dirs: list[str],
        contents: dict[str, str] | None = None,
    ) -> list[ThemeInfo]:
        contents = contents or {}
        candidates: dict[str, str] = {}  # theme base dir -> style.css path

        for path in paths:
            if not path.endswith("style.css"):
                continue
            if "/" not in path:
                # `style.css` at the repository root of a standalone theme repo.
                # Require the mandatory WordPress `Theme Name` header — otherwise
                # every plain HTML/CSS site (whose root stylesheet has no theme
                # headers) would be misreported as a theme.
                root_headers = parse_wp_headers(contents.get(path, ""), keys=_THEME_KEYS)
                if "theme name" in root_headers:
                    candidates["."] = path
                continue
            parent = path[: -len("/style.css")]
            match = _THEME_PATH_RE.search(parent)
            if not match:
                continue
            slug = match.group("slug")
            base = (match.group("base") or "") + "themes/" + slug
            candidates[base.rstrip("/")] = path

        themes: list[ThemeInfo] = []
        for base, style_path in sorted(candidates.items()):
            slug = "." if base == "." else base.rsplit("/", 1)[-1]
            css = contents.get(style_path, "")
            headers = parse_wp_headers(css, keys=_THEME_KEYS)

            template = headers.get("template")
            name = headers.get("theme name") or prettify_slug(slug)

            if template:
                theme_type = "child"
            elif not headers.get("theme name"):
                theme_type = "unknown"
            elif _known(slug):
                theme_type = "known"
            else:
                theme_type = "custom"

            root = "" if base == "." else base
            block_theme = bool(root) and any(
                p == f"{root}/theme.json" or p.endswith("/theme.json") and p.startswith(root + "/")
                for p in paths
            )
            has_functions = bool(root) and f"{root}/functions.php" in set(paths)

            themes.append(
                ThemeInfo(
                    name=name,
                    slug=slug,
                    location=f"{root}/" if root else "./",
                    version=headers.get("version"),
                    author=headers.get("author"),
                    description=headers.get("description"),
                    theme_type=theme_type,  # type: ignore[arg-type]
                    parent_theme=template,
                    block_theme=block_theme,
                    has_functions_php=has_functions,
                    text_domain=headers.get("text domain"),
                    headers=headers,
                )
            )
        return themes
