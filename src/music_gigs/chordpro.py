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
_HARMONY_RE = re.compile(r"<<([^>]+)>>")
_BAR_CHORD_RE = re.compile(r"\|([^|]+)\|")
_INLINE_NOTE_NAMES = frozenset({"c", "comment", "dir", "direction", "note"})
_PROGRESSION_INLINE_RE = re.compile(r"^progression:\s*(.+)$", re.I)
_STRUCTURE_COMMENT_RE = re.compile(r"^structure:\s*(.+)$", re.I)
_PROGRESSION_COMMENT_RE = re.compile(
    r"^progression(?:[_\s-]+([\w-]+))?:\s*(.+)$",
    re.I,
)
_CHORD_ROOT_RE = r"[A-G](?:[#b])?"
_CHORD_SUFFIX_RE = r"(?:maj7|min7|m7|7|m|sus2|sus4|add9|dim|aug)?"
_CHORD_NAME_BODY_RE = rf"{_CHORD_ROOT_RE}{_CHORD_SUFFIX_RE}"
_CHORD_TOKEN_RE = re.compile(
    rf"{_CHORD_NAME_BODY_RE}(?:/{_CHORD_NAME_BODY_RE})?"
)
_CHORD_NAME_RE = re.compile(rf"^{_CHORD_NAME_BODY_RE}(?:/{_CHORD_NAME_BODY_RE})?$")
_INLINE_CUE_ONLY_RE = re.compile(r"^\*(.+)$")
_CHORD_WITH_CUE_RE = re.compile(rf"^({_CHORD_NAME_BODY_RE}(?:/{_CHORD_NAME_BODY_RE})?)\*(.+)$")
_CHORD_WITH_ANNOTATION_RE = re.compile(
    rf"^({_CHORD_NAME_BODY_RE}(?:/{_CHORD_NAME_BODY_RE})?)(?:\s+(.+))?$"
)
_SEGMENT_MARKUP_RE = re.compile(
    r"<<(?P<harmony>[^>]+)>>"
    r"|"
    r"\{(?P<style>ti|text_italic|tb|text_bold):\s*(?P<direction>[^}]*)\}",
    re.I,
)
_REPEAT_SUFFIX_RE = re.compile(r"(?:\(x|x|×)\s*(\d+)\s*\)?\s*$", re.I)
_HARMONY_DIRECTIVE_NAMES = frozenset({"harmony", "harm", "bv"})
_LYRIC_SECTION_TYPES = frozenset(
    {"verse", "chorus", "bridge", "pre-chorus", "pre_chorus", "tag"}
)


def _format_section_type_name(section_type: str) -> str:
    return "-".join(part.capitalize() for part in section_type.replace("_", "-").split("-"))


def section_display_title(section_type: str, label: str = "", number: int | None = None) -> str:
    title = _format_section_type_name(section_type)
    if number is not None:
        title = f"{title} {number}"
    if label:
        title = f"{title} — {label}"
    return title


def _section_type_counts(sections: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for section in sections:
        section_type = section["type"]
        if section_type == "comment":
            continue
        counts[section_type] = counts.get(section_type, 0) + 1
    return counts


def section_numbers_for(sections: list[dict[str, Any]]) -> list[int | None]:
    """Number sections only when a song has 2+ of the same type."""
    totals = _section_type_counts(sections)
    tallies: dict[str, int] = {}
    numbers: list[int | None] = []
    for section in sections:
        section_type = section["type"]
        if section_type == "comment":
            numbers.append(None)
            continue
        tallies[section_type] = tallies.get(section_type, 0) + 1
        numbers.append(tallies[section_type] if totals[section_type] > 1 else None)
    return numbers


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

            if current_section is not None and name in _INLINE_NOTE_NAMES:
                current_section["lines"].append(f"{{__note__:{value}}}")
                continue

            if current_section is not None and name in _HARMONY_DIRECTIVE_NAMES:
                current_section["lines"].append(f"{{__harmony__:{value}}}")
                continue

            if name == "comment":
                structure_match = _STRUCTURE_COMMENT_RE.match(value)
                if structure_match:
                    song.metadata["structure"] = structure_match.group(1).strip()
                    continue
                progression_match = _PROGRESSION_COMMENT_RE.match(value)
                if progression_match:
                    section_key = (progression_match.group(1) or "default").lower().replace("-", "_")
                    song.metadata[f"progression_{section_key}"] = progression_match.group(2).strip()
                    continue
                song.sections.append({"type": "comment", "label": "", "lines": [value]})
                continue

            song.metadata[name] = value
            continue

        if current_section is not None:
            current_section["lines"].append(line)
        else:
            song.sections.append({"type": "lyric", "label": "", "lines": [line]})

    return song


def _parse_bracket_token(token: str) -> dict[str, str]:
    """Parse [Am], [STOP], [Dm7 (play twice)], [*STOP], or [G*STOP]."""
    token = token.strip()
    cue_only = _INLINE_CUE_ONLY_RE.match(token)
    if cue_only:
        return {"chord": "", "cue": cue_only.group(1).strip()}
    chord_cue = _CHORD_WITH_CUE_RE.match(token)
    if chord_cue:
        return {"chord": chord_cue.group(1), "cue": chord_cue.group(2).strip()}
    annotated = _CHORD_WITH_ANNOTATION_RE.match(token)
    if annotated and _CHORD_NAME_RE.match(annotated.group(1)):
        return {
            "chord": annotated.group(1),
            "cue": (annotated.group(2) or "").strip(),
        }
    if _CHORD_NAME_RE.match(token):
        return {"chord": token, "cue": ""}
    return {"chord": "", "cue": token}


def _strip_lyric_markup(line: str) -> str:
    plain = _CHORD_RE.sub("", line)
    # Strip harmony delimiters but keep inner text (closed or not) so chord
    # positions match rendered lyrics when chords sit inside <<...>>.
    plain = plain.replace("<<", "").replace(">>", "")
    plain = _SEGMENT_MARKUP_RE.sub("", plain)
    return plain


def _strip_chords_and_harmony(line: str) -> str:
    return _strip_lyric_markup(line)


def _chord_positions(line: str) -> tuple[str, list[dict[str, Any]]]:
    lyric_plain = _strip_chords_and_harmony(line)
    chords: list[dict[str, Any]] = []
    for match in _CHORD_RE.finditer(line):
        plain_before = _strip_chords_and_harmony(line[: match.start()])
        parsed = _parse_bracket_token(match.group(1))
        chords.append(
            {
                "pos": len(plain_before),
                "chord": parsed["chord"],
                "cue": parsed.get("cue") or "",
            }
        )
    return lyric_plain, chords


def _segment_same_style(left: dict[str, Any], right: dict[str, Any]) -> bool:
    if left.get("direction") or right.get("direction"):
        return False
    return left.get("harmony") == right.get("harmony")


def _merge_adjacent_segments(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not segments:
        return [{"text": "", "harmony": False, "direction": False}]
    merged: list[dict[str, Any]] = []
    for segment in segments:
        if merged and _segment_same_style(merged[-1], segment):
            merged[-1] = {
                **merged[-1],
                "text": merged[-1]["text"] + segment["text"],
            }
        else:
            merged.append(dict(segment))
    return merged


def _lyric_segments_with_harmony_spans(
    text: str, in_harmony: bool
) -> tuple[list[dict[str, Any]], bool]:
    """Parse << >> harmony markup, including spans that cross line breaks."""
    segments: list[dict[str, Any]] = []
    index = 0
    length = len(text)
    while index < length:
        if text.startswith("<<", index):
            in_harmony = True
            index += 2
            continue
        if text.startswith(">>", index):
            in_harmony = False
            index += 2
            continue
        next_open = text.find("<<", index)
        next_close = text.find(">>", index)
        candidates = [pos for pos in (next_open, next_close) if pos != -1]
        end = min(candidates) if candidates else length
        chunk = text[index:end]
        if chunk:
            if in_harmony:
                segments.append({"text": chunk, "harmony": True, "direction": False})
            else:
                segments.extend(_lyric_segments(chunk))
        index = end
    return _merge_adjacent_segments(segments), in_harmony


def _segments_for_line_markup(
    text: str, in_harmony: bool
) -> tuple[list[dict[str, Any]], bool]:
    if "<<" in text or ">>" in text or in_harmony:
        return _lyric_segments_with_harmony_spans(text, in_harmony)
    return _lyric_segments(text), in_harmony


def _lyric_segments(lyric_plain: str) -> list[dict[str, Any]]:
    segments: list[dict[str, Any]] = []
    last = 0
    for match in _SEGMENT_MARKUP_RE.finditer(lyric_plain):
        if match.start() > last:
            segments.append(
                {"text": lyric_plain[last : match.start()], "harmony": False, "direction": False}
            )
        if match.group("harmony") is not None:
            segments.append({"text": match.group("harmony"), "harmony": True, "direction": False})
        else:
            style = (match.group("style") or "").lower()
            segments.append(
                {
                    "text": (match.group("direction") or "").strip(),
                    "harmony": False,
                    "direction": True,
                    "bold": style in {"tb", "text_bold"},
                }
            )
        last = match.end()
    if last < len(lyric_plain):
        segments.append({"text": lyric_plain[last:], "harmony": False, "direction": False})
    return segments or [{"text": lyric_plain, "harmony": False, "direction": False}]


def _is_bar_notation(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("|") and "|" in stripped[1:]


def _is_chord_only_line(line: str) -> bool:
    if not _CHORD_RE.search(line):
        return False
    remainder = _CHORD_RE.sub("", line).strip()
    return not re.search(r"[A-Za-z]{2,}", remainder)


def _parse_bar_measures(text: str) -> tuple[list[str], int]:
    """One chord per |measure|; optional (x2) / x2 repeat suffix applies to the whole line."""
    repeat = 1
    repeat_match = _REPEAT_SUFFIX_RE.search(text)
    if repeat_match:
        repeat = int(repeat_match.group(1))
        text = text[: repeat_match.start()].strip()
    chords: list[str] = []
    for segment in text.split("|"):
        segment = segment.strip()
        if not segment or segment.startswith("("):
            continue
        for token in segment.split():
            if re.match(r"^[A-G]", token):
                chords.append(token)
                break
    return chords, repeat


def _chords_from_bar_notation(text: str) -> list[str]:
    chords, repeat = _parse_bar_measures(text)
    if not chords:
        return []
    return chords * repeat


def _compact_repeated_measures(measures: list[str]) -> list[dict[str, Any]]:
    """Turn |D|D| or |D|G|D|G| into D (×2) / D G (×2) for structure view."""
    count = len(measures)
    if not count:
        return []
    for period in range(1, count + 1):
        if count % period:
            continue
        pattern = measures[:period]
        reps = count // period
        if reps < 2:
            continue
        if all(measures[index : index + period] == pattern for index in range(0, count, period)):
            return [{"chords": pattern, "repeat": reps}]
    return [{"chords": measures, "repeat": 1}]


def _compact_from_bar_notation(text: str) -> list[dict[str, Any]]:
    chords, repeat = _parse_bar_measures(text)
    if not chords:
        return []
    measures = chords * repeat
    return _compact_repeated_measures(measures)


def _compact_from_lyric_line_pairs(
    chord_lines: list[list[dict[str, Any]]],
) -> list[dict[str, Any]] | None:
    """Pair consecutive lyric chord rows (e.g. D G + D A → D G D A)."""
    groups = [
        [entry["chord"] for entry in line if entry.get("chord")]
        for line in chord_lines
        if line
    ]
    if len(groups) < 2 or len(groups) % 2 != 0:
        return None
    if not all(len(group) >= 2 for group in groups):
        return None
    pairs = [groups[index] + groups[index + 1] for index in range(0, len(groups), 2)]
    collapsed: list[dict[str, Any]] = []
    for pair in pairs:
        if collapsed and collapsed[-1]["chords"] == pair:
            collapsed[-1]["repeat"] += 1
        else:
            collapsed.append({"chords": pair, "repeat": 1})
    return collapsed


def _parse_section_line(
    line: str, section_type: str = "", *, in_harmony: bool = False
) -> tuple[list[dict[str, Any]], bool]:
    stripped = line.strip()
    if stripped.startswith("{__note__:") and stripped.endswith("}"):
        text = stripped[10:-1]
        progression_match = _PROGRESSION_INLINE_RE.match(text)
        if progression_match:
            return [{"kind": "progression", "spec": progression_match.group(1).strip()}], in_harmony
        return [{"kind": "note", "text": text, "inline": True}], in_harmony
    if stripped.startswith("{__harmony__:") and stripped.endswith("}"):
        return [{"kind": "harmony", "text": stripped[13:-1]}], in_harmony

    if _is_bar_notation(line):
        return [{"kind": "bars", "text": line, "chords": _chords_from_bar_notation(line)}], in_harmony

    if _is_chord_only_line(line):
        _, chords = _chord_positions(line)
        return [{"kind": "chord_line", "chords": chords}], in_harmony

    if _CHORD_RE.search(line):
        lyrics, chords = _chord_positions(line)
        segment_source = _CHORD_RE.sub("", line).strip()
        segments, in_harmony = _segments_for_line_markup(segment_source, in_harmony)
        return [
            {
                "kind": "lyric",
                "lyrics": lyrics,
                "chords": chords,
                "segments": segments,
            }
        ], in_harmony

    if (
        _HARMONY_RE.search(line)
        or _SEGMENT_MARKUP_RE.search(line)
        or "<<" in line
        or ">>" in line
        or in_harmony
    ):
        stripped_line = line.strip()
        segment_source = _CHORD_RE.sub("", stripped_line)
        segments, in_harmony = _segments_for_line_markup(segment_source, in_harmony)
        return [
            {
                "kind": "lyric",
                "lyrics": _strip_lyric_markup(stripped_line).strip(),
                "chords": [],
                "segments": segments,
            }
        ], in_harmony

    if section_type in _LYRIC_SECTION_TYPES:
        text = line.rstrip()
        segments, in_harmony = _segments_for_line_markup(text, in_harmony)
        return [
            {
                "kind": "lyric",
                "lyrics": _strip_lyric_markup(text),
                "chords": [],
                "segments": segments,
            }
        ], in_harmony

    return [{"kind": "note", "text": line, "inline": False}], in_harmony


def _parse_section_blocks_from_lines(
    lines: list[str], section_type: str
) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    in_harmony = False
    for line in lines:
        new_blocks, in_harmony = _parse_section_line(
            line, section_type, in_harmony=in_harmony
        )
        blocks.extend(new_blocks)
    return _merge_chord_line_blocks(blocks)


def _merge_chord_line_blocks(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Pair chord-only rows with the lyric line below (classic chord-sheet layout)."""
    merged: list[dict[str, Any]] = []
    index = 0
    while index < len(blocks):
        block = blocks[index]
        if (
            block.get("kind") == "chord_line"
            and index + 1 < len(blocks)
            and blocks[index + 1].get("kind") == "lyric"
            and not blocks[index + 1].get("chords")
        ):
            lyric = blocks[index + 1]
            merged.append(
                {
                    "kind": "lyric",
                    "lyrics": lyric["lyrics"],
                    "chords": block["chords"],
                    "segments": lyric.get("segments") or _lyric_segments(lyric["lyrics"]),
                }
            )
            index += 2
            continue
        merged.append(block)
        index += 1
    return merged


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


def _entry_chord_line_text(entry: dict[str, Any], transpose: int = 0) -> str:
    parts: list[str] = []
    if entry.get("chord"):
        parts.append(transpose_chord(entry["chord"], transpose))
    if entry.get("cue"):
        parts.append(entry["cue"])
    return " ".join(parts)


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
        text = _entry_chord_line_text(entry, transpose)
        if text:
            items.append((entry["pos"], text))
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
        if not entry.get("chord"):
            continue
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
        chord = transpose_chord(entry.get("chord", ""), transpose) if entry.get("chord") else ""
        cue = entry.get("cue") or ""
        pos = entry["pos"]
        numeral = chord_to_nashville(chord, song_key) if show_nashville and chord else ""
        chord_html = (
            f'<span class="chord">{html.escape(chord)}</span>' if chord else ""
        )
        cue_html = (
            f'<span class="chord-cue">{html.escape(cue)}</span>' if cue else ""
        )
        num_html = ""
        if numeral:
            num_html = (
                f'<span class="nashville" style="width:{len(chord)}ch">'
                f"{html.escape(numeral)}</span>"
            )
        markers.append(
            f'<span class="chord-marker" style="left:{pos}ch">'
            f"{chord_html}{cue_html}{num_html}"
            f"</span>"
        )
    return f'<div class="chord-track">{"".join(markers)}</div>'


def _render_lyric_segments_html(segments: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for segment in segments:
        text = html.escape(segment["text"])
        if segment.get("harmony"):
            parts.append(f'<span class="harmony">{text}</span>')
        elif segment.get("direction"):
            css = "inline-direction"
            if segment.get("bold"):
                parts.append(f'<span class="{css}"><strong>{text}</strong></span>')
            else:
                parts.append(f'<span class="{css}">{text}</span>')
        else:
            parts.append(text)
    return "".join(parts)


def _collect_block_chords(block: dict[str, Any]) -> list[str]:
    kind = block.get("kind")
    if kind == "lyric":
        return [
            entry["chord"]
            for entry in block.get("chords", [])
            if entry.get("chord")
        ]
    if kind == "chord_line":
        return [
            entry["chord"]
            for entry in block.get("chords", [])
            if entry.get("chord")
        ]
    if kind == "bars":
        return list(block.get("chords", []))
    return []


def chordpro_to_structured(song: ChordProSong) -> list[dict[str, Any]]:
    """Export song sections for client-side rendering and transposition."""
    structured: list[dict[str, Any]] = []
    numbers = section_numbers_for(song.sections)

    for index, section in enumerate(song.sections):
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
            blocks = _parse_section_blocks_from_lines(lines, section_type)

        progression_override = None
        content_blocks: list[dict[str, Any]] = []
        for block in blocks:
            if block.get("kind") == "progression":
                progression_override = block["spec"]
            else:
                content_blocks.append(block)

        structured.append(
            {
                "type": section_type,
                "label": label,
                "number": numbers[index],
                "progression_override": progression_override,
                "blocks": content_blocks,
            }
        )

    return structured


_HINT_WORDS = 10


def _word_hint(text: str, *, from_end: bool = False) -> str:
    words = text.split()
    if not words:
        return ""
    if from_end:
        return " ".join(words[-_HINT_WORDS:])
    return " ".join(words[:_HINT_WORDS])


def progression_hints_from_metadata(metadata: dict[str, str]) -> dict[str, str]:
    hints: dict[str, str] = {}
    for key, value in metadata.items():
        if key.startswith("progression_"):
            section_key = key.removeprefix("progression_").lower().replace("-", "_")
            hints[section_key] = value
    return hints


def chart_structure_warnings(song: ChordProSong) -> list[str]:
    if song.metadata.get("structure"):
        return []
    title = song.metadata.get("title", "chart")
    return [
        f'{title}: no {{comment: Structure: ...}} hint — structure view uses best-guess chord detection'
    ]


def parse_progression_spec(text: str) -> dict[str, Any]:
    spec = text.strip()
    repeat = 1
    repeat_match = _REPEAT_SUFFIX_RE.search(spec)
    if repeat_match:
        repeat = int(repeat_match.group(1))
        spec = spec[: repeat_match.start()].strip()
    normalized = spec.replace("|", " ").replace("-", " ")
    chords = _CHORD_TOKEN_RE.findall(normalized)
    return {
        "pattern": chords,
        "repeat": repeat,
        "tail": [],
        "source": "override",
    }


def detect_repeating_progression(chords: list[str]) -> dict[str, Any]:
    """Find a repeating chord pattern at the start of a section (e.g. D G D A ×2)."""
    count = len(chords)
    if not count:
        return {"pattern": [], "repeat": 0, "tail": [], "source": "empty"}

    best_score = -1.0
    best: dict[str, Any] | None = None

    for period in range(1, count + 1):
        pattern = chords[:period]
        position = 0
        repeats = 0
        while position + period <= count and chords[position : position + period] == pattern:
            repeats += 1
            position += period
        remainder = chords[position:]
        if remainder and pattern[: len(remainder)] != remainder:
            continue
        if repeats < 1:
            continue

        score = repeats * 1000 + period * 10 - period * 0.01
        if repeats >= 2:
            score += 5000
        if len(remainder) > 0:
            score -= len(remainder) * 2

        if score > best_score:
            best_score = score
            best = {
                "pattern": pattern,
                "repeat": repeats,
                "tail": remainder,
                "source": "detected" if repeats >= 2 else "fallback",
            }

    if best and best["repeat"] >= 2:
        return best
    return {"pattern": chords, "repeat": 1, "tail": [], "source": "fallback"}


def progression_to_compact_rows(progression: dict[str, Any]) -> list[dict[str, Any]]:
    pattern = progression.get("pattern") or []
    if not pattern:
        return []
    rows = [{"chords": pattern, "repeat": progression.get("repeat", 1)}]
    tail = progression.get("tail") or []
    if tail:
        rows.append({"chords": tail, "repeat": 1})
    return rows


def _split_chord_row_for_display(row: list[str], max_per_line: int = 4) -> list[list[str]]:
    if len(row) <= max_per_line:
        return [row]
    if len(row) == 4:
        return [row[:2], row[2:]]
    if len(row) <= 8:
        mid = len(row) // 2
        return [row[:mid], row[mid:]]
    return [row[i : i + max_per_line] for i in range(0, len(row), max_per_line)]


def _compact_flat_sequence(chord_seq: list[str]) -> list[dict[str, Any]]:
    n = len(chord_seq)
    if not n:
        return []
    for period in (4, 2, 8, 3, 6):
        if n >= period * 2 and n % period == 0:
            pattern = chord_seq[:period]
            if all(chord_seq[i : i + period] == pattern for i in range(0, n, period)):
                rows = _split_chord_row_for_display(pattern)
                reps = n // period
                result: list[dict[str, Any]] = []
                for idx, row in enumerate(rows):
                    result.append({"chords": row, "repeat": reps if idx == len(rows) - 1 else 1})
                return result
    if n <= 4:
        return [{"chords": chord_seq, "repeat": 1}]
    rows = _split_chord_row_for_display(chord_seq)
    return [{"chords": row, "repeat": 1} for row in rows]


def _compact_sparse_lyric_progression(
    rows: list[list[str]], chord_seq: list[str]
) -> list[dict[str, Any]] | None:
    """One chord per lyric line (or a short tag) → G Am Em Cadd9, not a vertical list."""
    if not chord_seq or not rows:
        return None
    flat = [chord for row in rows for chord in row]
    if flat != chord_seq:
        return None
    if all(len(row) == 1 for row in rows):
        return _compact_flat_sequence(chord_seq)
    if (
        len(rows) >= 3
        and len(rows) <= 4
        and max(len(row) for row in rows) <= 2
        and len(chord_seq) <= 8
    ):
        return [{"chords": chord_seq, "repeat": 1}]
    return None


def _detect_alternating_pair_pattern(rows: list[list[str]]) -> list[dict[str, Any]] | None:
    if len(rows) < 4 or len(rows) % 2 != 0:
        return None
    first_pair = (rows[0], rows[1])
    for index in range(0, len(rows), 2):
        if (rows[index], rows[index + 1]) != first_pair:
            return None
    reps = len(rows) // 2
    return [
        {"chords": first_pair[0], "repeat": 1},
        {"chords": first_pair[1], "repeat": reps},
    ]


def compact_chord_rows(
    chord_lines: list[list[dict[str, Any]]],
    chord_seq: list[str],
    progression_override: str | None = None,
    bar_texts: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Group chords into compact rows for structure view, collapsing repeated patterns."""
    if progression_override:
        return progression_to_compact_rows(parse_progression_spec(progression_override))

    bar_rows: list[dict[str, Any]] = []
    if bar_texts:
        for text in bar_texts:
            bar_rows.extend(_compact_from_bar_notation(text))

    if bar_rows and not chord_lines:
        return bar_rows

    paired = _compact_from_lyric_line_pairs(chord_lines)
    if paired:
        return paired + bar_rows

    rows: list[list[str]] = [
        [entry["chord"] for entry in line] for line in chord_lines if line
    ]

    if chord_seq:
        detected = detect_repeating_progression(chord_seq)
        if detected.get("source") == "detected":
            return progression_to_compact_rows(detected) + bar_rows

    sparse = _compact_sparse_lyric_progression(rows, chord_seq)
    if sparse:
        return sparse + bar_rows

    if not rows and chord_seq:
        return progression_to_compact_rows(detect_repeating_progression(chord_seq)) + bar_rows

    if not rows:
        return bar_rows

    alternating = _detect_alternating_pair_pattern(rows)
    if alternating:
        return alternating + bar_rows

    collapsed: list[tuple[list[str], int]] = []
    for row in rows:
        if collapsed and collapsed[-1][0] == row:
            collapsed[-1] = (row, collapsed[-1][1] + 1)
        else:
            collapsed.append((row, 1))

    result: list[dict[str, Any]] = []
    for row, count in collapsed:
        split_rows = _split_chord_row_for_display(row)
        for idx, split in enumerate(split_rows):
            repeat = count if idx == len(split_rows) - 1 else 1
            result.append({"chords": split, "repeat": repeat})
    return result + bar_rows


def format_structure_chord_row(row: dict[str, Any]) -> str:
    text = " ".join(row.get("chords") or [])
    repeat = row.get("repeat") or 1
    if repeat > 1:
        text = f"{text} (×{repeat})"
    return text


def structure_flow_from_section(
    section: dict[str, Any],
    progression_override: str | None = None,
) -> list[dict[str, Any]]:
    """Notes and chord rows in chart order for structure / sidebar views."""
    flow: list[dict[str, Any]] = []
    chord_lines: list[list[dict[str, Any]]] = []
    chord_seq: list[str] = []
    bar_texts: list[str] = []

    def flush() -> None:
        nonlocal chord_lines, chord_seq, bar_texts
        if not chord_lines and not bar_texts and not chord_seq:
            return
        rows = compact_chord_rows(
            chord_lines,
            chord_seq,
            progression_override=progression_override,
            bar_texts=bar_texts or None,
        )
        for row in rows:
            flow.append(
                {
                    "type": "chords",
                    "chords": row["chords"],
                    "repeat": row.get("repeat", 1),
                }
            )
        chord_lines = []
        chord_seq = []
        bar_texts = []

    for block in section.get("blocks", []):
        kind = block.get("kind")
        if kind == "note":
            flush()
            flow.append({"type": "note", "text": block["text"]})
        elif kind == "progression":
            flush()
            for row in progression_to_compact_rows(parse_progression_spec(block["spec"])):
                flow.append(
                    {
                        "type": "chords",
                        "chords": row["chords"],
                        "repeat": row.get("repeat", 1),
                    }
                )
        elif kind == "bars":
            flush()
            for row in _compact_from_bar_notation(block["text"]):
                flow.append(
                    {
                        "type": "chords",
                        "chords": row["chords"],
                        "repeat": row.get("repeat", 1),
                    }
                )
        elif kind == "lyric":
            line_chords = [
                {
                    "chord": entry["chord"],
                    "pos": entry["pos"],
                    "cue": entry.get("cue") or "",
                }
                for entry in block.get("chords", [])
            ]
            if line_chords:
                chord_lines.append(line_chords)
            chord_seq.extend(
                entry["chord"]
                for entry in block.get("chords", [])
                if entry.get("chord")
            )
        elif kind == "chord_line":
            line_chords = [
                {
                    "chord": entry["chord"],
                    "pos": entry["pos"],
                    "cue": entry.get("cue") or "",
                }
                for entry in block.get("chords", [])
            ]
            if line_chords:
                chord_lines.append(line_chords)
            chord_seq.extend(
                entry["chord"]
                for entry in block.get("chords", [])
                if entry.get("chord")
            )
        elif kind == "harmony":
            continue
        elif kind in {"tab", "abc"}:
            flush()
            label = block.get("label") or kind
            first_line = block.get("text", "").splitlines()[0] if block.get("text") else ""
            flow.append(
                {
                    "type": "note",
                    "text": f"{label}: {first_line}" if first_line else label,
                }
            )
    flush()
    return flow


def section_outline_from_structured(
    structured: list[dict[str, Any]],
    progression_hints: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Compact per-section summary for instrumentalists (chords, hints, notes)."""
    outline: list[dict[str, Any]] = []

    for section in structured:
        section_type = section["type"]
        if section_type == "comment":
            continue

        lyric_lines: list[str] = []
        chord_seq: list[str] = []
        chord_lines: list[list[dict[str, Any]]] = []
        bar_texts: list[str] = []
        notes: list[str] = []

        for block in section.get("blocks", []):
            kind = block.get("kind")
            if kind == "lyric":
                lyric_lines.append(block["lyrics"])
                line_chords = [
                    {
                        "chord": entry["chord"],
                        "pos": entry["pos"],
                        "cue": entry.get("cue") or "",
                    }
                    for entry in block.get("chords", [])
                ]
                if line_chords:
                    chord_lines.append(line_chords)
                chord_seq.extend(
                    entry["chord"]
                    for entry in block.get("chords", [])
                    if entry.get("chord")
                )
            elif kind == "chord_line":
                line_chords = [
                    {
                        "chord": entry["chord"],
                        "pos": entry["pos"],
                        "cue": entry.get("cue") or "",
                    }
                    for entry in block.get("chords", [])
                ]
                if line_chords:
                    chord_lines.append(line_chords)
                chord_seq.extend(
                    entry["chord"]
                    for entry in block.get("chords", [])
                    if entry.get("chord")
                )
            elif kind == "bars":
                bar_texts.append(block["text"])
                bar_chords = _chords_from_bar_notation(block["text"])
                if bar_chords:
                    chord_seq.extend(bar_chords)
            elif kind == "note":
                notes.append(block["text"])
            elif kind in {"tab", "abc"}:
                label = block.get("label") or kind
                first_line = block.get("text", "").splitlines()[0] if block.get("text") else ""
                notes.append(f"{label}: {first_line}" if first_line else label)

        hint_lyrics = " ".join(lyric_lines).strip()
        word_count = len(hint_lyrics.split())
        section_key = section_type.lower().replace("-", "_")
        override = section.get("progression_override")
        if not override and progression_hints:
            override = progression_hints.get(section_key) or progression_hints.get("default")
        chord_compact = compact_chord_rows(
            chord_lines,
            chord_seq,
            progression_override=override,
            bar_texts=bar_texts,
        )
        outline.append(
            {
                "type": section_type,
                "label": section.get("label", ""),
                "number": section.get("number"),
                "chords": chord_seq,
                "chord_lines": chord_lines,
                "chord_compact": chord_compact,
                "flow": structure_flow_from_section(section, override),
                "progression_source": "override" if override else "detected",
                "start": _word_hint(hint_lyrics),
                "end": _word_hint(hint_lyrics, from_end=True) if word_count > _HINT_WORDS else "",
                "notes": notes,
            }
        )

    return outline


def _render_lyric_line(
    line: str,
    song_key: str = "C",
    transpose: int = 0,
    show_nashville: bool = False,
) -> str:
    """Render chords on a line above the lyrics (classic chart layout)."""
    blocks, _ = _parse_section_line(line)
    block = blocks[0]
    if block["kind"] != "lyric":
        return ""

    lyric_plain = block["lyrics"]
    chords = block["chords"]
    segments = block.get("segments") or _lyric_segments(lyric_plain)
    if not chords:
        return (
            f'<div class="lyric-row lyrics-only"><div class="lyrics">'
            f"{_render_lyric_segments_html(segments)}</div></div>"
        )

    chord_html = _render_chord_track_html(
        chords, song_key, transpose, show_nashville=show_nashville
    )
    return (
        f'<div class="lyric-row">{chord_html}'
        f'<div class="lyrics">{_render_lyric_segments_html(segments)}</div></div>'
    )


def _render_block_html(
    block: dict[str, Any],
    song_key: str = "C",
    transpose: int = 0,
    show_nashville: bool = False,
) -> str:
    kind = block.get("kind")
    if kind == "lyric":
        lyric_plain = block["lyrics"]
        chords = block.get("chords", [])
        segments = block.get("segments") or _lyric_segments(lyric_plain)
        if not chords:
            return (
                f'<div class="lyric-row lyrics-only"><div class="lyrics">'
                f"{_render_lyric_segments_html(segments)}</div></div>"
            )
        chord_html = _render_chord_track_html(
            chords, song_key, transpose, show_nashville=show_nashville
        )
        return (
            f'<div class="lyric-row">{chord_html}'
            f'<div class="lyrics">{_render_lyric_segments_html(segments)}</div></div>'
        )
    if kind == "note":
        css = "inline-direction" if block.get("inline") else "note"
        return f'<p class="{css}">{html.escape(block["text"])}</p>'
    if kind == "harmony":
        return f'<p class="harmony-line">{html.escape(block["text"])}</p>'
    if kind == "progression":
        return f'<p class="inline-direction">progression: {html.escape(block["spec"])}</p>'
    if kind == "bars":
        return f'<p class="bars">{html.escape(block["text"])}</p>'
    if kind == "chord_line":
        chords = block.get("chords", [])
        items = "  ".join(
            transpose_chord(entry["chord"], transpose) for entry in chords
        )
        return f'<p class="chord-line">{html.escape(items)}</p>'
    return ""


def render_chordpro_html(song: ChordProSong) -> str:
    chunks: list[str] = []
    numbers = section_numbers_for(song.sections)

    for index, section in enumerate(song.sections):
        section_type = section["type"]
        label = section.get("label", "")
        lines = section.get("lines", [])
        number = numbers[index]

        if section_type == "comment":
            chunks.append(f'<p class="note">{html.escape(" ".join(lines))}</p>')
            continue

        section_parts: list[str] = []

        if section_type in {"tab", "abc"} or section_type.startswith("tab:"):
            title = label or section_type
            body = html.escape("\n".join(lines))
            css_class = "tab" if "tab" in section_type else "abc"
            section_parts.append(f'<h3 class="section-label">{html.escape(title)}</h3>')
            section_parts.append(f'<pre class="{css_class}">{body}</pre>')
            chunks.append(
                f'<section class="chart-section">{"".join(section_parts)}</section>'
            )
            continue

        if section_type in {"intro", "outro", "bridge", "verse", "chorus"} or section_type:
            title = section_display_title(section_type, label, number)
            section_parts.append(f'<h3 class="section-label">{html.escape(title)}</h3>')

        block_class = "lyric-block"
        if section_type in {"intro", "outro"}:
            block_class = "note-block"

        section_blocks = _parse_section_blocks_from_lines(lines, section_type)
        section_blocks = [
            block
            for block in section_blocks
            if block["kind"] not in {"tab", "abc"}
        ]

        line_html = []
        for block in section_blocks:
            rendered = _render_block_html(block)
            if rendered:
                line_html.append(rendered)

        if line_html:
            section_parts.append(f'<div class="{block_class}">{"".join(line_html)}</div>')

        if section_parts:
            chunks.append(
                f'<section class="chart-section">{"".join(section_parts)}</section>'
            )

    return "\n".join(chunks)
