from __future__ import annotations

from backend.scanner.file_classifier import classify, is_indexable, language_for


def test_classify_php_file():
    result = classify("wp-content/themes/x/functions.php", 120)
    assert result.category == "php"
    assert result.language == "php"
    assert result.is_source is True
    assert result.is_binary is False
    assert result.is_wordpress_file is True


def test_classify_styles_and_scripts():
    assert classify("assets/css/main.css").category == "css"
    assert classify("assets/scss/main.scss").category == "scss"
    assert classify("assets/js/app.js").category == "javascript"
    assert classify("src/components/Button.tsx").category == "typescript"


def test_classify_images_and_fonts_are_binary():
    image = classify("img/logo.png")
    assert image.category == "image"
    assert image.is_binary is True
    assert is_indexable(image) is False

    font = classify("fonts/inter.woff2")
    assert font.category == "font"
    assert is_indexable(font) is False


def test_classify_json_yaml_markdown():
    assert classify("composer.json").category == "json"
    assert classify(".github/workflows/ci.yml").category == "yaml"
    assert classify("README.md").category == "markdown"


def test_wordpress_specific_names():
    assert classify("wp-config.php").is_wordpress_file is True
    assert classify("header.php").is_wordpress_file is True
    assert classify("404.php").is_wordpress_file is True
    assert classify("front-page.php").is_wordpress_file is True
    # style.css is only WordPress specific inside a theme path
    assert classify("wp-content/themes/x/style.css").is_wordpress_file is True
    assert classify("public/style.css").is_wordpress_file is False
    # a generic PHP file is not WordPress specific
    assert classify("src/Service.php").is_wordpress_file is False


def test_language_for_and_indexable():
    assert language_for("a/b.php") == "php"
    assert language_for("a/b.png") is None
    assert is_indexable(classify("wp-config-sample.php")) is True
    assert is_indexable(classify("dist/bundle.min.js")) is True
