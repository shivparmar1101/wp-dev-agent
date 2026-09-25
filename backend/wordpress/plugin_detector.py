from __future__ import annotations

import re

from backend.models.project import PluginInfo
from backend.utils.helpers import parse_wp_headers, prettify_slug

_PLUGIN_KEYS = (
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
)

KNOWN_PLUGINS = {
    "elementor",
    "elementor-pro",
    "contact-form-7",
    "wp-mail-smtp",
    "woocommerce",
    "wordpress-seo",
    "wp-seo",
    "wordfence",
    "classic-editor",
    "jetpack",
    "wpforms-lite",
    "ninja-forms",
    "advanced-custom-fields",
    "duplicate-post",
    "w3-total-cache",
    "wp-super-cache",
    "litespeed-cache",
    "autoptimize",
    "really-simple-ssl",
    "redirection",
    "updraftplus",
    "query-monitor",
    "akismet",
    "hello-dolly",
    "wp-optimize",
    "revslider",
    "js_composer",
    "wp-rocket",
    "sg-cachepress",
    "complianz-gdpr",
    "cookie-notice",
    "mailchimp-for-wp",
    "tablepress",
    "ewww-image-optimizer",
    "shortcodes-ultimate",
    "wordpress-popular-posts",
    "redux-framework",
}

_PLUGIN_DIR_RE = re.compile(r"(?:^|/)(?P<base>.*/)?plugins/(?P<slug>[^/]+)$")
_MU_PLUGIN_RE = re.compile(r"(?:^|/)(?P<base>.*/)?mu-plugins/(?P<file>[^/]+\.php)$")


class PluginDetector:
    """Identifies WordPress plugins from directory structure + plugin headers."""

    def detect(
        self,
        *,
        paths: list[str],
        dirs: list[str],
        contents: dict[str, str] | None = None,
    ) -> list[PluginInfo]:
        contents = contents or {}
        path_set = sorted(set(paths))
        plugins: dict[str, PluginInfo] = {}

        # Group paths per plugin directory.
        plugin_dirs: dict[str, list[str]] = {}
        for path in path_set:
            if "/" not in path:
                continue
            parent = path.rsplit("/", 1)[0]
            match = _PLUGIN_DIR_RE.search(parent)
            if not match:
                continue
            slug = match.group("slug")
            base = ((match.group("base") or "") + "plugins/" + slug).rstrip("/")
            plugin_dirs.setdefault(base, []).append(path)

        for base, member_paths in sorted(plugin_dirs.items()):
            slug = base.rsplit("/", 1)[-1]
            php_files = [p for p in member_paths if p.lower().endswith(".php")]
            if not php_files:
                continue

            main_file = None
            preferred = f"{base}/{slug}.php"
            if preferred in member_paths:
                main_file = preferred
            else:
                # Shallowest PHP file is usually the bootstrap file.
                root_php = sorted(
                    (p for p in php_files if p.count("/") == base.count("/") + 1),
                    key=len,
                )
                main_file = root_php[0] if root_php else None

            headers: dict[str, str] = {}
            source = "directory"
            if main_file and main_file in contents:
                headers = parse_wp_headers(contents[main_file], keys=_PLUGIN_KEYS)
                if headers.get("plugin name"):
                    source = "plugin_header"
                else:
                    headers = {}
            if source == "directory":
                # Fall back to any root PHP file that carries a plugin header.
                for candidate in sorted(
                    (p for p in php_files if p.count("/") == base.count("/") + 1), key=len
                ):
                    parsed = parse_wp_headers(contents.get(candidate, ""), keys=_PLUGIN_KEYS)
                    if parsed.get("plugin name"):
                        headers = parsed
                        main_file = candidate
                        source = "plugin_header"
                        break

            name = headers.get("plugin name") or prettify_slug(slug)
            plugins[slug] = PluginInfo(
                name=name,
                slug=slug,
                location=f"{base}/",
                version=headers.get("version"),
                author=headers.get("author"),
                description=headers.get("description"),
                text_domain=headers.get("text domain"),
                main_file=main_file,
                known=slug in KNOWN_PLUGINS,
                metadata_source=source,  # type: ignore[arg-type]
                headers=headers,
            )

        # Single-file must-use plugins: wp-content/mu-plugins/*.php
        for path in path_set:
            match = _MU_PLUGIN_RE.search(path)
            if not match:
                continue
            file_name = match.group("file")
            content = contents.get(path, "")
            headers = parse_wp_headers(content, keys=_PLUGIN_KEYS) if content else {}
            if not headers.get("plugin name") and not content:
                # Not read yet - still surface the file with directory metadata.
                headers = {}
            slug = file_name[:-4] if file_name.endswith(".php") else file_name
            if slug in plugins:
                continue
            plugins[slug] = PluginInfo(
                name=headers.get("plugin name") or prettify_slug(slug),
                slug=slug,
                location=path,
                version=headers.get("version"),
                author=headers.get("author"),
                description=headers.get("description"),
                text_domain=headers.get("text domain"),
                main_file=path,
                known=slug in KNOWN_PLUGINS,
                metadata_source="plugin_header" if headers.get("plugin name") else "directory",
                headers=headers,
            )

        return sorted(plugins.values(), key=lambda p: p.name.lower())
