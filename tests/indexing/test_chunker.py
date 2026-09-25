from __future__ import annotations

from backend.indexing.chunker import chunk_file, snippet_for


def test_single_small_file_is_one_chunk():
    content = "\n".join(f"line {i}" for i in range(1, 21))
    chunks = chunk_file(content, "a.php", "php", max_lines=100, overlap=10)
    assert len(chunks) == 1
    assert chunks[0].start_line == 1
    assert chunks[0].end_line == 20
    assert chunks[0].language == "php"


def test_chunk_boundaries_and_overlap():
    content = "\n".join(f"line {i}" for i in range(1, 301))
    chunks = chunk_file(content, "big.php", "php", max_lines=100, overlap=10, max_chars=100000)
    assert len(chunks) == 4
    assert chunks[0].start_line == 1
    assert chunks[0].end_line == 100
    # overlapping windows preserve continuity
    assert chunks[1].start_line < chunks[0].end_line
    assert chunks[-1].end_line == 300
    for previous, current in zip(chunks, chunks[1:]):
        assert current.start_line <= previous.end_line
        assert current.start_line > previous.start_line


def test_line_numbers_allow_precise_citations():
    content = "\n".join(f"line {i}" for i in range(1, 401))
    chunks = chunk_file(content, "x.css", "css", max_lines=50, overlap=5, max_chars=100000)
    for chunk in chunks:
        lines = chunk.content.splitlines()
        assert len(lines) == chunk.end_line - chunk.start_line + 1
        assert lines[0] == f"line {chunk.start_line}"


def test_minified_single_line_falls_back_to_char_windows():
    content = "." + "a" * 20000
    chunks = chunk_file(content, "bundle.min.js", "javascript", max_chars=6000)
    assert len(chunks) >= 3
    assert all(c.start_line == 1 for c in chunks)


def test_empty_content_returns_no_chunks():
    assert chunk_file("", "a.php", "php") == []


def test_truncation_respects_max_chars():
    content = "x" * 500 + "\n" + "y" * 5000
    chunks = chunk_file(content, "a.css", "css", max_lines=10, overlap=0, max_chars=1000)
    assert all(len(c.content) <= 1000 for c in chunks)


def test_snippet_for_returns_surrounding_lines():
    content = "\n".join(f"line {i}" for i in range(1, 41))
    text, start, end = snippet_for(content, needle="line 20", context_lines=3)
    assert start == 17
    assert end == 23
    assert "line 20" in text
