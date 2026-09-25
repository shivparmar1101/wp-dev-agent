from __future__ import annotations

from pathlib import PurePosixPath

from backend.models.file import FileClassification

# extension -> (category, language)
_EXTENSION_MAP: dict[str, tuple[str, str]] = {
    # PHP
    ".php": ("php", "php"),
    ".phtml": ("php", "php"),
    ".inc": ("php", "php"),
    ".module": ("php", "php"),
    ".php3": ("php", "php"),
    ".php4": ("php", "php"),
    ".php5": ("php", "php"),
    ".phps": ("php", "php"),
    ".ctp": ("php", "php"),
    # Styles
    ".css": ("css", "css"),
    ".scss": ("scss", "scss"),
    ".sass": ("scss", "sass"),
    ".less": ("scss", "less"),
    # JavaScript
    ".js": ("javascript", "javascript"),
    ".mjs": ("javascript", "javascript"),
    ".cjs": ("javascript", "javascript"),
    ".jsx": ("javascript", "jsx"),
    ".vue": ("javascript", "vue"),
    ".svelte": ("javascript", "svelte"),
    # TypeScript
    ".ts": ("typescript", "typescript"),
    ".tsx": ("typescript", "tsx"),
    ".mts": ("typescript", "typescript"),
    ".cts": ("typescript", "typescript"),
    # Markup
    ".html": ("html", "html"),
    ".htm": ("html", "html"),
    ".xhtml": ("html", "html"),
    ".twig": ("html", "twig"),
    ".liquid": ("html", "liquid"),
    ".mustache": ("html", "mustache"),
    ".hbs": ("html", "handlebars"),
    # Data
    ".json": ("json", "json"),
    ".jsonc": ("json", "json"),
    ".yml": ("yaml", "yaml"),
    ".yaml": ("yaml", "yaml"),
    ".xml": ("xml", "xml"),
    ".rss": ("xml", "xml"),
    ".atom": ("xml", "xml"),
    # Docs
    ".md": ("markdown", "markdown"),
    ".mdx": ("markdown", "markdown"),
    ".markdown": ("markdown", "markdown"),
    ".rst": ("markdown", "restructuredtext"),
    ".txt": ("other", "text"),
    # Config
    ".ini": ("configuration", "ini"),
    ".conf": ("configuration", "conf"),
    ".cfg": ("configuration", "cfg"),
    ".properties": ("configuration", "properties"),
    ".toml": ("configuration", "toml"),
    ".lock": ("configuration", "text"),
    ".dist": ("configuration", "text"),
    # Images
    ".png": ("image", "binary"),
    ".jpg": ("image", "binary"),
    ".jpeg": ("image", "binary"),
    ".gif": ("image", "binary"),
    ".webp": ("image", "binary"),
    ".avif": ("image", "binary"),
    ".ico": ("image", "binary"),
    ".bmp": ("image", "binary"),
    ".tiff": ("image", "binary"),
    ".psd": ("image", "binary"),
    ".svg": ("image", "binary"),
    # Fonts
    ".woff": ("font", "binary"),
    ".woff2": ("font", "binary"),
    ".ttf": ("font", "binary"),
    ".otf": ("font", "binary"),
    ".eot": ("font", "binary"),
    # Archives / media / misc binary
    ".zip": ("other", "binary"),
    ".gz": ("other", "binary"),
    ".tar": ("other", "binary"),
    ".rar": ("other", "binary"),
    ".7z": ("other", "binary"),
    ".pdf": ("other", "binary"),
    ".mp3": ("other", "binary"),
    ".mp4": ("other", "binary"),
    ".webm": ("other", "binary"),
    ".mov": ("other", "binary"),
    ".woff2.map": ("other", "binary"),
}

_CONFIG_FILENAMES = {
    "dockerfile",
    "makefile",
    "gemfile",
    "rakefile",
    "procfile",
    ".gitignore",
    ".gitattributes",
    ".editorconfig",
    ".eslintrc",
    ".eslintrc.js",
    ".eslintrc.json",
    ".prettierrc",
    ".prettierrc.json",
    ".babelrc",
    ".bowerrc",
    ".nvmrc",
    ".tool-versions",
    ".htaccess",
    ".htpasswd",
    "webpack.config.js",
    "vite.config.js",
    "vite.config.ts",
    "next.config.js",
    "next.config.mjs",
    "tailwind.config.js",
    "tailwind.config.ts",
    "postcss.config.js",
}

# WordPress template / core files recognised by name (spec section 8).
WORDPRESS_FILE_NAMES = {
    "wp-config.php",
    "functions.php",
    "header.php",
    "footer.php",
    "single.php",
    "page.php",
    "archive.php",
    "404.php",
    "front-page.php",
    "index.php",
    "search.php",
    "category.php",
    "tag.php",
    "author.php",
    "date.php",
    "attachment.php",
    "home.php",
    "sidebar.php",
    "comments.php",
    "searchform.php",
    "wp-load.php",
    "wp-blog-header.php",
    "wp-settings.php",
    "template-parts",
}

WORDPRESS_PATH_HINTS = (
    "/wp-content/",
    "/wp-admin/",
    "/wp-includes/",
    "wp-content/themes/",
    "wp-content/plugins/",
    "wp-content/mu-plugins/",
)

_INDEXABLE_CATEGORIES = {
    "php",
    "css",
    "scss",
    "javascript",
    "typescript",
    "html",
    "json",
    "yaml",
    "xml",
    "markdown",
    "configuration",
    "other",
}

_SOURCE_CATEGORIES = _INDEXABLE_CATEGORIES - {"other"} | {"other"}


def extension_of(path: str) -> str:
    name = PurePosixPath(path).name
    if name.startswith(".") and name.count(".") == 1:
        return name  # dotfiles such as .gitignore
    return PurePosixPath(name).suffix.lower()


def classify(path: str, size: int | None = None) -> FileClassification:
    """Classify a repository path into a category + language."""
    name = PurePosixPath(path).name
    ext = extension_of(path)
    lowered_path = "/" + path.lower().strip("/")

    category, language = _EXTENSION_MAP.get(ext, ("other", "text"))

    if name.lower() in _CONFIG_FILENAMES:
        category = "configuration"
        language = "configuration"
    elif ext == "" and name.upper() in {"Dockerfile", "MAKEFILE"}:
        category = "configuration"

    is_binary = category in {"image", "font"} or language == "binary"

    # Special case: style.css is only WordPress-specific inside a theme.
    wordpress_named = False
    lowered_name = name.lower()
    if lowered_name in WORDPRESS_FILE_NAMES:
        wordpress_named = True
    elif lowered_name == "style.css" and any(hint in lowered_path for hint in WORDPRESS_PATH_HINTS):
        wordpress_named = True

    is_source = (not is_binary) and category in _INDEXABLE_CATEGORIES

    return FileClassification(
        path=path,
        name=name,
        extension=ext,
        category=category,
        language=language,
        is_source=is_source,
        is_binary=is_binary,
        is_wordpress_file=wordpress_named,
        size=size,
    )


def is_indexable(classification: FileClassification) -> bool:
    return bool(
        classification.is_source
        and not classification.is_binary
        and classification.category in _INDEXABLE_CATEGORIES
    )


def language_for(path: str) -> str | None:
    classification = classify(path)
    return classification.language if classification.is_source else None
