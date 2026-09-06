from __future__ import annotations

import html
import re
from dataclasses import dataclass, field


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


def _render_lyric_line(line: str) -> str:
    """Render chords on a line above the lyrics (classic chart layout)."""
    lyric_plain = _plain_lyric_line(line)
    if not _CHORD_RE.search(line):
        return f'<div class="lyric-row lyrics-only"><div class="lyrics">{html.escape(lyric_plain)}</div></div>'

    chord_chars = [" "] * len(lyric_plain)
    for match in _CHORD_RE.finditer(line):
        plain_before = _plain_lyric_line(line[: match.start()])
        pos = len(plain_before)
        chord = match.group(1)
        for i, ch in enumerate(chord):
            idx = pos + i
            if idx < len(chord_chars):
                chord_chars[idx] = ch
            else:
                chord_chars.extend([" "] * (idx - len(chord_chars)))
                chord_chars.append(ch)

    chord_line = "".join(chord_chars).rstrip()
    return (
        f'<div class="lyric-row">'
        f'<div class="chords">{html.escape(chord_line)}</div>'
        f'<div class="lyrics">{html.escape(lyric_plain)}</div>'
        f"</div>"
    )


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
