"""Infer ChordPro sections from flat CountryTabs-style line lists."""

from __future__ import annotations

import re
from typing import Any

from music_gigs.countrytabs import _INLINE_CHORD_RE, _SECTION_RE, _SECTION_TYPE_MAP

_TAB_STAFF_RE = re.compile(r"^\|[\dbr\-/ ]+\|$", re.IGNORECASE)
_EMAIL_RE = re.compile(r"@|\.com\b", re.IGNORECASE)
_INTRO_LABEL_RE = re.compile(r"^\s*intro\s*:", re.IGNORECASE)
_OUTRO_LABEL_RE = re.compile(r"^\s*outro\s*:", re.IGNORECASE)
_SOLO_LABEL_RE = re.compile(r"^\s*solo\s*:", re.IGNORECASE)
_CHORD_ONLY_RE = re.compile(r"^(\[[^\]]+\]\s*)+$")
_LYRIC_RE = re.compile(r"[A-Za-z]{2,}")


def _section_type(label: str) -> str:
    normalized = re.sub(r"\s+", " ", label.strip().lower()).rstrip(":")
    for prefix, section_type in _SECTION_TYPE_MAP.items():
        if normalized.startswith(prefix):
            return section_type
    return "verse"


def _has_lyrics(line: str) -> bool:
    plain = _INLINE_CHORD_RE.sub("", line)
    return bool(_LYRIC_RE.search(plain))


def _is_chord_only(line: str) -> bool:
    if not _INLINE_CHORD_RE.search(line):
        return False
    return not _has_lyrics(line)


def _is_junk_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return True
    if _TAB_STAFF_RE.match(stripped):
        return True
    if _EMAIL_RE.search(stripped):
        return True
    if re.match(r"^by\s+", stripped, re.IGNORECASE):
        return True
    if re.match(r"^https?://", stripped, re.IGNORECASE):
        return True
    return False


def _is_title_header(line: str, title: str, artist: str) -> bool:
    lowered = line.lower()
    title_l = title.lower()
    artist_l = artist.lower()
    if title_l in lowered and (artist_l.split()[0] in lowered or "key of" in lowered):
        return True
    return False


def cleanup_import_lines(
    lines: list[str],
    *,
    title: str = "",
    artist: str = "",
) -> list[str]:
    """Drop tab staff junk and header noise; turn stage notes into {c:} lines."""
    cleaned: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if _is_junk_line(stripped):
            continue
        if title and artist and _is_title_header(stripped, title, artist):
            continue
        if re.match(r"^play\s+", stripped, re.IGNORECASE) or re.match(
            r"^i use this\b", stripped, re.IGNORECASE
        ):
            cleaned.append(f"{{c: {stripped}}}")
            continue
        cleaned.append(stripped)
    return cleaned


def chart_content_matches(title: str, lines: list[str]) -> bool:
    """Heuristic: imported lyrics should mention words from the song title."""
    text = " ".join(lines).lower()
    tokens = [word for word in re.findall(r"[a-z']{4,}", title.lower()) if word not in {"with", "the", "and"}]
    if not tokens:
        return True
    return any(token in text for token in tokens)


def _logical_rows(lines: list[str]) -> list[list[str]]:
    rows: list[list[str]] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if _is_chord_only(line) and index + 1 < len(lines) and _has_lyrics(lines[index + 1]):
            rows.append([line, lines[index + 1]])
            index += 2
            continue
        rows.append([line])
        index += 1
    return rows


def _rows_to_lines(rows: list[list[str]]) -> list[str]:
    return [part for row in rows for part in row]


def _detect_chorus_rows(rows: list[list[str]], min_repeat: int = 2) -> set[int]:
    """Return row indexes that belong to a repeated chorus block."""
    signatures: list[tuple[str, ...]] = []
    for row in rows:
        text = " ".join(_INLINE_CHORD_RE.sub("", part) for part in row).lower()
        text = re.sub(r"[^a-z' ]+", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) < 20:
            continue
        signatures.append(tuple(text.split()[:8]))

    chorus_rows: set[int] = set()
    for size in (4, 3, 2):
        counts: dict[tuple[tuple[str, ...], ...], list[int]] = {}
        for start in range(0, len(signatures) - size + 1):
            block = tuple(signatures[start : start + size])
            counts.setdefault(block, []).append(start)
        for starts in counts.values():
            if len(starts) >= min_repeat:
                for start in starts:
                    for offset in range(size):
                        chorus_rows.add(start + offset)
    return chorus_rows


def _split_intro(rows: list[list[str]]) -> tuple[list[list[str]], list[list[str]]]:
    intro: list[list[str]] = []
    body = rows
    while body:
        row = body[0]
        joined = " ".join(row)
        if _INTRO_LABEL_RE.match(joined):
            intro.append(body.pop(0))
            continue
        if any(part.strip().startswith("{c:") for part in row):
            intro.append(body.pop(0))
            continue
        if len(row) == 1 and _is_chord_only(row[0]):
            intro.append(body.pop(0))
            continue
        if len(row) == 1 and _has_lyrics(row[0]) and "|" in row[0] and _INLINE_CHORD_RE.search(row[0]):
            intro.append(body.pop(0))
            continue
        break
    return intro, body


def infer_sections(
    lines: list[str],
    *,
    stanza_rows: int = 4,
) -> list[tuple[str, list[str]]]:
    """Turn a flat line list into section tuples (type, lines)."""
    sections: list[tuple[str, list[str]]] = []
    current_type = "verse"
    current_lines: list[str] = []

    def flush() -> None:
        nonlocal current_lines
        if current_lines:
            sections.append((current_type, current_lines))
            current_lines = []

    for line in lines:
        section_match = _SECTION_RE.match(line)
        if section_match:
            flush()
            current_type = _section_type(section_match.group(1))
            continue
        if _INTRO_LABEL_RE.match(line):
            flush()
            current_type = "intro"
            current_lines.append(re.sub(r"^intro:\s*", "", line, flags=re.IGNORECASE))
            continue
        if _OUTRO_LABEL_RE.match(line):
            flush()
            current_type = "outro"
            current_lines.append(re.sub(r"^outro:\s*", "", line, flags=re.IGNORECASE))
            continue
        if _SOLO_LABEL_RE.match(line):
            flush()
            current_type = "solo"
            current_lines.append(re.sub(r"^solo:\s*", "", line, flags=re.IGNORECASE))
            continue
        current_lines.append(line)

    flush()
    if len(sections) > 1:
        return sections

    if not sections:
        return [("verse", lines)]

    only_type, only_lines = sections[0]
    if only_type != "verse" or len(only_lines) < stanza_rows * 2:
        return sections

    rows = _logical_rows(only_lines)
    intro_rows, body_rows = _split_intro(rows)
    if not body_rows:
        return sections

    chorus_rows = _detect_chorus_rows(body_rows)
    result: list[tuple[str, list[str]]] = []
    if intro_rows:
        result.append(("intro", _rows_to_lines(intro_rows)))

    chunk: list[list[str]] = []
    chunk_type = "verse"

    def flush_chunk() -> None:
        nonlocal chunk, chunk_type
        if chunk:
            result.append((chunk_type, _rows_to_lines(chunk)))
            chunk = []

    for index, row in enumerate(body_rows):
        row_type = "chorus" if index in chorus_rows else "verse"
        if chunk and row_type != chunk_type:
            flush_chunk()
        chunk_type = row_type
        chunk.append(row)
        if row_type == "verse" and len(chunk) >= stanza_rows:
            flush_chunk()
            chunk_type = "verse"

    flush_chunk()
    return result or sections


def structure_outline(sections: list[tuple[str, list[str]]]) -> str:
    """Build a compact structure hint like I V C V C B C."""
    letter_map = {
        "intro": "I",
        "verse": "V",
        "chorus": "C",
        "bridge": "B",
        "outro": "O",
        "solo": "S",
        "prechorus": "P",
        "tag": "T",
    }
    parts: list[str] = []
    for section_type, _lines in sections:
        letter = letter_map.get(section_type, section_type[:1].upper())
        parts.append(letter)
    return " ".join(parts)


def enrich_sections_metadata(
    sections: list[tuple[str, list[str]]],
    *,
    add_structure_comment: bool = True,
) -> dict[str, Any]:
    outline = structure_outline(sections)
    return {
        "sections": sections,
        "structure": outline if add_structure_comment else "",
    }
