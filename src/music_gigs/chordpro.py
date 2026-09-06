from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from typing import Any

from music_gigs.chords import chord_to_nashville, transpose_chord


@dataclass
class ChordProSong:
    metadata: dict[str, str] = field(default_factory=dict)
    sections: list[dict[str, str]] = field(default_factory=list)


_DIRECTIVE_RE = re.compile(r"^\{([^}:]+)(?::\s*(.*))?\}$")
_CHORD_RE = re.compile(r"\[([^\]]+)\]")


def parse_chordpro(text: str) -> ChordProSong:
    song = ChordProSong()
    current_section: dict[str, str] | None = None

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            continue

        directive = _DIRECTIVE_RE.match(stripped)
        if directive:
            name = directive.group(1).strip().lower()
            value = (directive.group(2) or "").strip()

            if name.startswith("start_of_"):
                section_type = name.removeprefix("start_of_")
                current_section = {"type": section_type, "label": value, "lines": []}
                song.sections.append(current_section)
                continue

            if name == "end_of" or name.startswith("end_of_"):
                current_section = None
                continue

            if name == "comment":
                song.sections.append({"type": "comment", "label": "", "lines": [value]})
                continue

            song.metadata[name] = value
            continue

        if current_section is not None:
            current_section["lines"].append(line)
        else:
            song.sections.append({"type": "lyric", "label": "", "lines": [line]})

    return song


def _plain_lyric_line(line: str) -> str:
    return _CHORD_RE.sub("", line)


def _chord_positions(line: str) -> tuple[str, list[dict[str, Any]]]:
    lyric_plain = _plain_lyric_line(line)
    chords: list[dict[str, Any]] = []
    for match in _CHORD_RE.finditer(line):
        plain_before = _plain_lyric_line(line[: match.start()])
        chords.append({"pos": len(plain_before), "chord": match.group(1)})
    return lyric_plain, chords


def _write_positioned_line(lyric_plain: str, items: list[tuple[int, str]]) -> str:
    if not items:
        return ""
    chars = [" "] * len(lyric_plain)
    for pos, text in items:
        for i, ch in enumerate(text):
            idx = pos + i
            if idx < len(chars):
                chars[idx] = ch
            else:
                chars.extend([" "] * (idx - len(chars)))
                chars.append(ch)
    return "".join(chars).rstrip()


def _build_chord_line(
    lyric_plain: str,
    chords: list[dict[str, Any]],
    song_key: str,
    transpose: int = 0,
) -> str:
    if not chords:
        return ""
    items: list[tuple[int, str]] = []
    for entry in chords:
        chord = transpose_chord(entry["chord"], transpose)
        items.append((entry["pos"], chord))
    return _write_positioned_line(lyric_plain, items)


def _build_nashville_line(
    lyric_plain: str,
    chords: list[dict[str, Any]],
    song_key: str,
    transpose: int = 0,
) -> str:
    if not chords:
        return ""
    items: list[tuple[int, str]] = []
    for entry in chords:
        chord = transpose_chord(entry["chord"], transpose)
        numeral = chord_to_nashville(chord, song_key)
        if numeral:
            offset = max(0, (len(chord) - len(numeral)) // 2)
            items.append((entry["pos"] + offset, numeral))
    return _write_positioned_line(lyric_plain, items)


def _render_chord_track_html(
    chords: list[dict[str, Any]],
    song_key: str,
    transpose: int = 0,
    show_nashville: bool = False,
) -> str:
    markers: list[str] = []
    for entry in chords:
        chord = transpose_chord(entry["chord"], transpose)
        pos = entry["pos"]
        numeral = chord_to_nashville(chord, song_key) if show_nashville else ""
        num_html = ""
        if numeral:
            num_html = (
                f'<span class="nashville" style="width:{len(chord)}ch">'
                f"{html.escape(numeral)}</span>"
            )
        markers.append(
            f'<span class="chord-marker" style="left:{pos}ch">'
            f'<span class="chord">{html.escape(chord)}</span>'
            f"{num_html}"
            f"</span>"
        )
    return f'<div class="chord-track">{"".join(markers)}</div>'


def chordpro_to_structured(song: ChordProSong) -> list[dict[str, Any]]:
    """Export song sections for client-side rendering and transposition."""
    structured: list[dict[str, Any]] = []

    for section in song.sections:
        section_type = section["type"]
        label = section.get("label", "")
        lines = section.get("lines", [])
        blocks: list[dict[str, Any]] = []

        if section_type == "comment":
            blocks.append({"kind": "note", "text": " ".join(lines)})
        elif section_type in {"tab", "abc"}:
            blocks.append(
                {
                    "kind": section_type,
                    "label": label or section_type,
                    "text": "\n".join(lines),
                }
            )
        else:
            for line in lines:
                if _CHORD_RE.search(line):
                    lyrics, chords = _chord_positions(line)
                    blocks.append({"kind": "lyric", "lyrics": lyrics, "chords": chords})
                else:
                    blocks.append({"kind": "note", "text": line})

        structured.append({"type": section_type, "label": label, "blocks": blocks})

    return structured


def _render_lyric_line(
    line: str,
    song_key: str = "C",
    transpose: int = 0,
    show_nashville: bool = False,
) -> str:
    """Render chords on a line above the lyrics (classic chart layout)."""
    lyric_plain, chords = _chord_positions(line)
    if not chords:
        return f'<div class="lyric-row lyrics-only"><div class="lyrics">{html.escape(lyric_plain)}</div></div>'

    chord_line = _build_chord_line(lyric_plain, chords, song_key, transpose)
    if show_nashville:
        parts = [
            _render_chord_track_html(chords, song_key, transpose, show_nashville=True)
        ]
    else:
        parts = [f'<div class="chords">{html.escape(chord_line)}</div>']
    parts.append(f'<div class="lyrics">{html.escape(lyric_plain)}</div>')
    return f'<div class="lyric-row">{"".join(parts)}</div>'


def render_chordpro_html(song: ChordProSong) -> str:
    chunks: list[str] = []

    for section in song.sections:
        section_type = section["type"]
        label = section.get("label", "")
        lines = section.get("lines", [])

        if section_type == "comment":
            chunks.append(
                f'<p class="note">{html.escape(" ".join(lines))}</p>'
            )
            continue

        if section_type in {"tab", "abc"} or section_type.startswith("tab:"):
            title = label or section_type
            body = html.escape("\n".join(lines))
            css_class = "tab" if "tab" in section_type else "abc"
            chunks.append(f'<h3 class="section-label">{html.escape(title)}</h3>')
            chunks.append(f'<pre class="{css_class}">{body}</pre>')
            continue

        if section_type in {"intro", "outro", "bridge", "verse", "chorus"} or section_type:
            title = section_type.replace("_", " ").title()
            if label:
                title = f"{title} — {label}"
            chunks.append(f'<h3 class="section-label">{html.escape(title)}</h3>')

        block_class = "lyric-block"
        if section_type in {"intro", "outro"}:
            block_class = "note-block"

        line_html = []
        for line in lines:
            if _CHORD_RE.search(line):
                line_html.append(_render_lyric_line(line))
            else:
                line_html.append(f'<p class="note">{html.escape(line)}</p>')

        if line_html:
            chunks.append(f'<div class="{block_class}">{"".join(line_html)}</div>')

    return "\n".join(chunks)
