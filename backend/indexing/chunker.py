from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Chunk:
    file_path: str
    start_line: int
    end_line: int
    content: str
    language: str | None = None
    index: int = 0
    truncated: bool = False
    tokens: list[str] | None = field(default=None, repr=False, compare=False)

    @property
    def key(self) -> str:
        return f"{self.file_path}:{self.start_line}-{self.end_line}"


def _line_offsets(lines: list[str]) -> list[int]:
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line) + 1)
    return offsets


def _offset_to_line(offsets: list[int], offset: int) -> int:
    """1-based line number for a character offset (binary search)."""
    low, high = 0, len(offsets) - 1
    while low < high:
        mid = (low + high + 1) // 2
        if offsets[mid] <= offset:
            low = mid
        else:
            high = mid - 1
    return low + 1


def chunk_file(
    content: str,
    file_path: str,
    language: str | None = None,
    *,
    max_lines: int = 120,
    overlap: int = 20,
    max_chars: int = 6000,
) -> list[Chunk]:
    """Split a source file into overlapping line-aware chunks.

    Metadata (`start_line`, `end_line`) is preserved so AI answers can cite
    exact locations.
    """
    if not content:
        return []

    lines = content.splitlines()
    if not lines:
        return []

    max_lines = max(1, max_lines)
    overlap = max(0, min(overlap, max_lines - 1))

    # Single-line minified files: fall back to character windows.
    if len(lines) == 1 and len(lines[0]) > max_chars:
        return _chunk_single_line(lines[0], file_path, language, max_chars)

    chunks: list[Chunk] = []
    total = len(lines)
    start = 0
    index = 0

    while start < total:
        end = min(start + max_lines, total)
        # Prefer breaking on a blank line near the end of the window.
        if end < total:
            for probe in range(end, max(start + max_lines // 2, end - max_lines // 4), -1):
                if probe - 1 <= start:
                    break
                if not lines[probe - 1].strip():
                    end = probe
                    break
        chunk_lines = lines[start:end]
        text = "\n".join(chunk_lines)
        truncated = False
        if len(text) > max_chars:
            trimmed: list[str] = []
            used = 0
            for line in chunk_lines:
                if used + len(line) + 1 > max_chars:
                    truncated = True
                    break
                trimmed.append(line)
                used += len(line) + 1
            if not trimmed:
                trimmed = [chunk_lines[0][:max_chars]]
                truncated = True
            chunk_lines = trimmed
            text = "\n".join(chunk_lines)
            end = start + len(chunk_lines)

        chunks.append(
            Chunk(
                file_path=file_path,
                start_line=start + 1,
                end_line=end,
                content=text,
                language=language,
                index=index,
                truncated=truncated,
            )
        )
        index += 1
        if end >= total:
            break
        next_start = max(end - overlap, start + 1)
        start = next_start
    return chunks


def _chunk_single_line(
    line: str, file_path: str, language: str | None, max_chars: int
) -> list[Chunk]:
    chunks: list[Chunk] = []
    offset = 0
    index = 0
    while offset < len(line):
        window = line[offset : offset + max_chars]
        chunks.append(
            Chunk(
                file_path=file_path,
                start_line=1,
                end_line=1,
                content=window,
                language=language,
                index=index,
                truncated=offset + max_chars < len(line),
            )
        )
        index += 1
        offset += max_chars
    return chunks


def snippet_for(
    content: str,
    *,
    needle: str | None = None,
    context_lines: int = 6,
    max_chars: int = 600,
) -> tuple[str, int, int]:
    """Extract a snippet around `needle`. Returns (text, start_line, end_line).

    Line numbers are relative to `content` (1-based).
    """
    lines = content.splitlines() or [content]
    target_index = 0
    if needle:
        for index, line in enumerate(lines):
            if needle in line:
                target_index = index
                break
        else:
            for index, line in enumerate(lines):
                if needle.lower() in line.lower():
                    target_index = index
                    break

    start = max(0, target_index - context_lines)
    end = min(len(lines), target_index + context_lines + 1)
    text = "\n".join(lines[start:end])
    if len(text) > max_chars:
        text = text[:max_chars]
        truncated_lines = text.count("\n") + 1
        end = start + truncated_lines
    return text, start + 1, end
