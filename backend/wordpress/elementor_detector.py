from __future__ import annotations

from backend.models.project import ElementorDetection, WordPressDetection
from backend.utils.logging import get_logger

logger = get_logger(__name__)

_DIR_SIGNALS: list[tuple[str, float, str]] = [
    ("plugins/elementor/", 0.55, "Elementor plugin directory detected"),
    ("plugins/elementor-pro/", 0.55, "Elementor Pro plugin directory detected"),
    ("mu-plugins/elementor", 0.35, "Elementor must-use plugin directory detected"),
]

_PRO_PATH_MARKERS = (
    "plugins/elementor-pro/",
    "elementor-pro/modules/",
    "/elementor-pro/",
)

_CONTENT_SIGNALS: list[tuple[str, float, str, str]] = [
    # (needle, weight, evidence, target)  target: any | pro | css | php | js
    ("\\Elementor\\Plugin", 0.15, "Elementor Plugin class referenced in PHP", "php"),
    ("Elementor\\Plugin::instance", 0.15, "Elementor Plugin::instance() referenced", "php"),
    ("\\ElementorPro\\", 0.25, "Elementor Pro PHP namespace referenced", "pro"),
    ("extends \\Elementor\\Widget_Base", 0.15, "Custom widget extends \\Elementor\\Widget_Base", "php"),
    ("extends \\Widget_Base", 0.12, "Custom widget extends Widget_Base", "php"),
    ("_elementor_edit_mode", 0.10, "_elementor_edit_mode meta key referenced", "php"),
    ("_elementor_data", 0.10, "_elementor_data meta key referenced", "php"),
    ("_elementor_css", 0.08, "_elementor_css meta key referenced", "php"),
    ("elementor-location-", 0.10, "Elementor theme location referenced", "php"),
    ("elementor_front_end", 0.10, "elementor_front_end hooks referenced", "php"),
    ("elementorFrontend", 0.10, "elementorFrontend JavaScript object referenced", "js"),
    ("elementorPro", 0.12, "elementorPro JavaScript object referenced", "js"),
    (".elementor-element", 0.20, "Elementor CSS classes found (.elementor-element*)", "css"),
    (".elementor-widget", 0.15, "Elementor widget CSS classes found (.elementor-widget*)", "css"),
    (".elementor-container", 0.12, "Elementor container CSS classes found", "css"),
    (".elementor-section", 0.12, "Elementor section CSS classes found", "css"),
    ("data-elementor-type", 0.20, "data-elementor-type attribute found in markup", "any"),
    ("elementor-element elementor-element-", 0.20, "Elementor element markup found", "any"),
]

_MAX_EVIDENCE = 12
# Confidence needed to claim Elementor is present without a plugin directory.
_CONTENT_DETECTION_THRESHOLD = 0.35


def _ext(path: str) -> str:
    return path.rsplit("/", 1)[-1].rsplit(".", 1)[-1].lower() if "." in path.rsplit("/", 1)[-1] else ""


class ElementorDetector:
    """Detects Elementor and Elementor Pro from structure + code evidence."""

    def detect(
        self,
        *,
        paths: list[str],
        dirs: list[str],
        contents: dict[str, str] | None = None,
        wordpress: WordPressDetection | None = None,
    ) -> ElementorDetection:
        contents = contents or {}
        evidence: list[str] = []
        signals: dict[str, float] = {}
        confidence = 0.0
        pro_confidence = 0.0

        all_paths = [p.lower() for p in paths]
        all_dirs = [d.lower().rstrip("/") + "/" for d in dirs]

        # 1. Plugin directories
        for fragment, weight, label in _DIR_SIGNALS:
            matched = any(fragment in p for p in all_dirs) or any(fragment in p for p in all_paths)
            if matched:
                signals[label] = weight
                evidence.append(label)
                confidence += weight
                if "pro" in fragment:
                    pro_confidence += weight

        # 2. Paths referencing elementor (modules, assets)
        elementor_paths = [p for p in all_paths if "/elementor" in p or p.startswith("elementor")]
        if elementor_paths and not any("plugin directory" in e for e in evidence):
            signals["Elementor related files present"] = 0.20
            evidence.append("Elementor related files present")
            confidence += 0.20
        if any(marker in p for p in all_paths for marker in _PRO_PATH_MARKERS):
            pro_confidence += 0.20
            if "Elementor Pro files present" not in evidence:
                evidence.append("Elementor Pro files present")
                signals["Elementor Pro files present"] = 0.20

        # 3. Content markers
        for path, text in contents.items():
            if not text:
                continue
            ext = _ext(path)
            lowered_path = path.lower()
            for needle, weight, label, target in _CONTENT_SIGNALS:
                if label in evidence:
                    continue
                if target == "css" and ext not in ("css", "scss", "less"):
                    continue
                if target == "php" and ext not in ("php", "inc", "twig"):
                    continue
                if target == "js" and ext not in ("js", "jsx", "ts", "tsx", "mjs", "vue"):
                    continue
                if needle.lower() not in text.lower() and needle not in text:
                    continue
                evidence.append(f"{label} ({lowered_path})")
                signals[label] = weight
                confidence += weight
                if target == "pro" or "elementor-pro" in lowered_path:
                    pro_confidence += weight
                if len(evidence) >= _MAX_EVIDENCE:
                    break
            if len(evidence) >= _MAX_EVIDENCE:
                break

        confidence = round(min(1.0, confidence), 3)
        pro_confidence = round(min(1.0, pro_confidence), 3)

        wp_known = wordpress is not None and wordpress.is_wordpress
        has_directory = any("plugin directory" in e for e in evidence)
        if confidence >= _CONTENT_DETECTION_THRESHOLD or has_directory:
            elementor_status = "detected"
        elif wordpress is None:
            elementor_status = "unknown"
        elif wp_known:
            elementor_status = "not_detected"
        else:
            elementor_status = "unknown"

        if pro_confidence >= 0.4 or any("Elementor Pro plugin directory" in e for e in evidence):
            pro_status = "detected"
        elif elementor_status == "detected":
            pro_status = "not_detected"
        elif wp_known:
            pro_status = "not_detected"
        else:
            pro_status = "unknown"

        if not evidence:
            evidence.append("No Elementor structures or references found in scanned files")

        labels = {
            "detected": "Detected",
            "not_detected": "Not Detected",
            "unknown": "Unknown",
        }
        indicators = [
            f"Elementor: {labels[elementor_status]}",
            f"Elementor Pro: {labels[pro_status]}",
            f"Confidence: {confidence:.2f}",
        ]

        return ElementorDetection(
            elementor=elementor_status,  # type: ignore[arg-type]
            elementor_pro=pro_status,  # type: ignore[arg-type]
            confidence=confidence,
            evidence=evidence,
            indicators=indicators,
            signals=signals,
        )
