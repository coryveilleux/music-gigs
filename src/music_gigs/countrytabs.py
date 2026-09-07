from __future__ import annotations

import html
import re
import ssl
import urllib.error
import urllib.request
from pathlib import Path

from music_gigs.chords import semitones_between_keys, transpose_chord

_CHORDLINK_RE = re.compile(
    r"<a[^>]*class=['\"]chordlink['\"][^>]*>([^<]*)</a>",
    re.IGNORECASE,
)
_INLINE_CHORD_RE = re.compile(r"\[([^\]]+)\]")
_SECTION_RE = re.compile(
    r"^\s*(?:\(?\s*)?"
    r"(verse\s*\d*|chorus\s*\d*|bridge|intro|outro|solo|tag|refrain|pre-?chorus|interlude)"
    r"(?:\s*\d*)?[^)]*\)?\s*:?\s*$",
    re.IGNORECASE,
)
_SECTION_TYPE_MAP = {
    "verse": "verse",
    "chorus": "chorus",
    "bridge": "bridge",
    "intro": "intro",
    "outro": "outro",
    "solo": "solo",
    "tag": "tag",
    "refrain": "chorus",
    "pre-chorus": "prechorus",
    "prechorus": "prechorus",
    "interlude": "bridge",
}


def fetch_tablature(url: str, *, timeout: float = 30.0) -> str:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (compatible; music-gigs/1.0)"},
    )
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    try:
        with urllib.request.urlopen(request, context=context, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Failed to fetch {url}: {exc}") from exc

    for encoding in ("utf-8", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def extract_pre_html(page_html: str) -> str:
    match = re.search(r"<pre>(.*?)</pre>", page_html, re.IGNORECASE | re.DOTALL)
    if not match:
        raise ValueError("No <pre> chord block found on page")
    return match.group(1)


def pre_html_to_lines(pre_html: str) -> list[str]:
    text = _CHORDLINK_RE.sub(lambda match: f"[{match.group(1).strip()}]", pre_html)
    text = re.sub(r"<span[^>]*>.*?</span>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    lines: list[str] = []
    for raw_line in text.split("\n"):
        line = raw_line.rstrip()
        line = re.sub(r"[^\S\n]+", " ", line).strip()
        if line:
            lines.append(line)
    return lines


def _section_type(label: str) -> str:
    normalized = re.sub(r"\s+", " ", label.strip().lower())
    normalized = normalized.rstrip(":")
    for prefix, section_type in _SECTION_TYPE_MAP.items():
        if normalized.startswith(prefix):
            return section_type
    return "verse"


def _transpose_line(line: str, semitones: int) -> str:
    if semitones == 0:
        return line

    def replace(match: re.Match[str]) -> str:
        chord = match.group(1).strip()
        if not chord or chord.startswith("$"):
            return match.group(0)
        return f"[{transpose_chord(chord, semitones)}]"

    return _INLINE_CHORD_RE.sub(replace, line)


def lines_to_chordpro(
    lines: list[str],
    *,
    title: str,
    artist: str,
    key: str,
    source_url: str,
    transpose_semitones: int = 0,
    extra_comments: list[str] | None = None,
) -> str:
    if not lines:
        raise ValueError("No chord/lyric lines extracted")

    metadata_end = 0
    for index, line in enumerate(lines[:12]):
        if _INLINE_CHORD_RE.search(line) or _SECTION_RE.match(line):
            metadata_end = index
            break
    else:
        metadata_end = min(5, len(lines))

    body_lines = lines[metadata_end:]
    sections: list[tuple[str, list[str]]] = []
    current_type = "verse"
    current_lines: list[str] = []

    def flush() -> None:
        nonlocal current_lines
        if current_lines:
            sections.append((current_type, current_lines))
            current_lines = []

    for line in body_lines:
        section_match = _SECTION_RE.match(line)
        if section_match:
            flush()
            current_type = _section_type(section_match.group(1))
            continue

        if line.startswith("|") and _INLINE_CHORD_RE.search(line):
            current_lines.append(_transpose_line(line, transpose_semitones))
            continue

        if _INLINE_CHORD_RE.search(line) or any(ch.isalpha() for ch in line):
            current_lines.append(_transpose_line(line, transpose_semitones))

    flush()
    if not sections:
        sections = [("verse", [_transpose_line(line, transpose_semitones) for line in body_lines])]

    output: list[str] = [
        f"{{title: {title}}}",
        f"{{artist: {artist}}}",
        f"{{key: {key}}}",
        f"{{comment: Imported from CountryTabs — verify key and arrangement}}",
        f"{{comment: Source: {source_url}}}",
    ]
    for comment in extra_comments or []:
        output.append(f"{{comment: {comment}}}")

    for section_type, section_lines in sections:
        output.append("")
        output.append(f"{{start_of_{section_type}}}")
        output.extend(section_lines)
        output.append(f"{{end_of_{section_type}}}")

    return "\n".join(output).rstrip() + "\n"


def import_tablature_to_chordpro(
    url: str,
    *,
    title: str,
    artist: str,
    key: str,
    source_key: str | None = None,
    extra_comments: list[str] | None = None,
) -> str:
    page_html = fetch_tablature(url)
    pre_html = extract_pre_html(page_html)
    lines = pre_html_to_lines(pre_html)
    semitones = 0
    if source_key:
        semitones = semitones_between_keys(source_key, key)
    return lines_to_chordpro(
        lines,
        title=title,
        artist=artist,
        key=key,
        source_url=url,
        transpose_semitones=semitones,
        extra_comments=extra_comments,
    )


def is_chart_stub(chart_path: Path) -> bool:
    if not chart_path.exists():
        return True
    text = chart_path.read_text(encoding="utf-8")
    return "[TBD]" in text or "Chart pending" in text


def validate_tab_url(url: str) -> bool:
    try:
        extract_pre_html(fetch_tablature(url))
        return True
    except (OSError, ValueError, RuntimeError):
        return False


def preserved_chart_comments(chart_path: Path) -> list[str]:
    if not chart_path.exists():
        return []
    comments: list[str] = []
    for line in chart_path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("{comment:"):
            continue
        value = line.removeprefix("{comment:").removesuffix("}").strip()
        lowered = value.lower()
        if "chart pending" in lowered:
            continue
        if "imported from countrytabs" in lowered:
            continue
        if lowered.startswith("source:"):
            continue
        comments.append(value)
    return comments
