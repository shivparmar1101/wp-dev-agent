from __future__ import annotations

from pydantic import BaseModel, Field

from backend.models.project import WordPressDetection

from .repository_scanner import ScanResult


class ProjectDetection(BaseModel):
    types: list[str] = Field(default_factory=list)
    indicators: list[str] = Field(default_factory=list)
    primary: str = "unknown"


_SIGNALS: list[tuple[str, str, tuple[str, ...]]] = [
    ("wordpress", "WordPress application", ("wp-config.php", "wp-load.php", "wp-blog-header.php")),
    ("wordpress", "WordPress application", ("wp-content/", "wp-admin/", "wp-includes/")),
    ("node", "Node.js project", ("package.json",)),
    ("php-composer", "PHP Composer project", ("composer.json",)),
    ("python", "Python project", ("requirements.txt", "pyproject.toml")),
    ("ruby", "Ruby project", ("Gemfile",)),
    ("dotnet", ".NET project", ("*.sln", "*.csproj")),
    ("static-site", "Static website", ("index.html",)),
    ("shopify", "Shopify theme", ("layout/theme.liquid", "templates/")),
    ("astro", "Astro project", ("astro.config.mjs", "astro.config.ts")),
    ("nextjs", "Next.js project", ("next.config.js", "next.config.mjs", "next.config.ts")),
    ("laravel", "Laravel application", ("artisan", "app/Http/Kernel.php")),
    ("drupal", "Drupal project", ("web/sites/default/settings.php", "core/lib/Drupal.php")),
]


class ProjectDetector:
    """High level project type detection (complements WordPress detection)."""

    def detect(self, scan: ScanResult, wordpress: WordPressDetection | None = None) -> ProjectDetection:
        paths = set(scan.all_paths)
        dirset = set(scan.dirs)
        indicators: list[str] = []
        types: list[str] = []

        for project_type, label, signals in _SIGNALS:
            matched = False
            for signal in signals:
                if signal.endswith("/"):
                    matched = any(p.startswith(signal.rstrip("/")) or p + "/" == signal for p in dirset) or any(
                        p.startswith(signal) for p in paths
                    )
                elif signal.startswith("*"):
                    matched = any(fnmatch_name(p, signal) for p in paths)
                else:
                    matched = any(p == signal or p.endswith("/" + signal) for p in paths)
                if matched:
                    indicators.append(f"{label}: {signal} detected")
                    if project_type not in types:
                        types.append(project_type)
                    break

        if wordpress is not None and wordpress.is_wordpress:
            if "wordpress" not in types:
                types.insert(0, "wordpress")
            if not any(i.startswith("WordPress") for i in indicators):
                indicators.insert(0, "WordPress detection returned positive")

        primary = types[0] if types else "unknown"
        return ProjectDetection(types=types, indicators=indicators, primary=primary)


def fnmatch_name(path: str, pattern: str) -> bool:
    import fnmatch

    name = path.rsplit("/", 1)[-1]
    return fnmatch.fnmatch(name, pattern)
