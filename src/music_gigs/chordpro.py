from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from typing import Any

from music_gigs.chart_sections import structure_outline
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
                if _STRUCTURE_COMMENT_RE.match(value):
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


def _should_pair_lyric_chord_lines(groups: list[list[str]]) -> bool:
    if len(groups) < 2 or len(groups) % 2 != 0:
        return False
    if not all(len(group) >= 2 for group in groups):
        return False
    if all(len(group) == 2 for group in groups):
        return True
    lengths = {len(group) for group in groups}
    if len(lengths) == 1 and next(iter(lengths)) >= 4:
        return False
    return True


def _compact_from_lyric_line_pairs(
    chord_lines: list[list[dict[str, Any]]],
) -> list[dict[str, Any]] | None:
    """Pair consecutive lyric chord rows (e.g. D G + D A → D G D A)."""
    groups = [
        [entry["chord"] for entry in line if entry.get("chord")]
        for line in chord_lines
        if line
    ]
    if not _should_pair_lyric_chord_lines(groups):
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


def structure_form_from_structured(structured: list[dict[str, Any]]) -> str:
    """Compact form line (I V C …) from ChordPro section directives."""
    sections = [
        (section["type"], [])
        for section in structured
        if section["type"] not in {"comment", "tab", "abc"}
    ]
    return structure_outline(sections)


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


_STRUCTURE_CUE_LABELS: dict[str, str] = {
    "STOP": "Stop",
    "FULL BAND": "Full band",
    "HOLD": "Hold",
}


def _normalize_cue_text(cue: str) -> str:
    text = cue.strip()
    if text.startswith("(") and text.endswith(")"):
        text = text[1:-1].strip()
    return re.sub(r"\s+", " ", text)


def _structure_direction_label(cue: str) -> str:
    normalized = _normalize_cue_text(cue).upper()
    if normalized in _STRUCTURE_CUE_LABELS:
        return _STRUCTURE_CUE_LABELS[normalized]
    plain = _normalize_cue_text(cue)
    if plain.isupper():
        return plain.title()
    return plain


def _ordinal_word(n: int) -> str:
    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _structure_note_for_cue(chord_names: list[str], chord_index: int, cue: str) -> str:
    direction = _structure_direction_label(cue)
    if not chord_names or chord_index < 0 or chord_index >= len(chord_names):
        return direction
    chord = chord_names[chord_index]
    matches = [index for index, name in enumerate(chord_names) if name == chord]
    if len(matches) == 1:
        return f"{direction} on {chord}"
    position = matches.index(chord_index)
    if position == 0:
        return f"{direction} on first {chord}"
    if position == len(matches) - 1:
        return f"{direction} on last {chord}"
    return f"{direction} on {_ordinal_word(position + 1)} {chord}"


def _chord_names_on_line(line: list[dict[str, Any]]) -> list[str]:
    return [entry["chord"] for entry in line if entry.get("chord")]


def _global_chord_index_in_span(
    chord_lines: list[list[dict[str, Any]]],
    line_index: int,
    chord_index: int,
    span_start: int,
    span_end: int,
) -> int:
    cursor = 0
    for line_i in range(span_start, span_end):
        count = len(_chord_names_on_line(chord_lines[line_i]))
        if line_i == line_index:
            return cursor + chord_index
        cursor += count
    return 0


def _cycles_with_inline_cues(
    chord_lines: list[list[dict[str, Any]]],
    span_start: int,
    span_end: int,
    lines_per_cycle: int,
) -> set[int]:
    cycles: set[int] = set()
    for line_i in range(span_start, span_end):
        if _inline_cues_on_line(chord_lines[line_i]):
            cycles.add((line_i - span_start) // lines_per_cycle)
    return cycles


def _inline_cues_on_line(line: list[dict[str, Any]]) -> list[tuple[int, str]]:
    """Chord-index and cue text for each inline direction on one lyric row."""
    names = _chord_names_on_line(line)
    events: list[tuple[int, str]] = []
    chord_count = 0
    pending_cue: str | None = None
    for entry in line:
        cue = _normalize_cue_text(entry.get("cue") or "")
        chord = entry.get("chord") or ""
        if chord:
            if pending_cue:
                events.append((chord_count, pending_cue))
                pending_cue = None
            if cue:
                events.append((chord_count, cue))
            chord_count += 1
        elif cue:
            if chord_count > 0:
                events.append((chord_count - 1, cue))
            else:
                pending_cue = cue
    if pending_cue and chord_count > 0:
        events.append((chord_count - 1, pending_cue))
    return events


def _active_chord_line_indices(chord_lines: list[list[dict[str, Any]]]) -> list[int]:
    return [
        index
        for index, line in enumerate(chord_lines)
        if line and any(entry.get("chord") for entry in line)
    ]


def _line_span_for_chord_range(
    chord_lines: list[list[dict[str, Any]]],
    start_chord: int,
    end_chord: int,
) -> tuple[int, int]:
    cursor = 0
    first_line: int | None = None
    last_exclusive = 0
    for index, line in enumerate(chord_lines):
        count = len(_chord_names_on_line(line))
        if not count:
            continue
        line_start = cursor
        line_end = cursor + count
        if line_end > start_chord and first_line is None:
            first_line = index
        if line_start < end_chord:
            last_exclusive = index + 1
        cursor = line_end
    if first_line is None:
        return (0, len(chord_lines))
    return (first_line, last_exclusive)


def _compact_from_lyric_line_pairs_with_spans(
    chord_lines: list[list[dict[str, Any]]],
) -> list[dict[str, Any]] | None:
    indexed = [
        (index, _chord_names_on_line(line))
        for index, line in enumerate(chord_lines)
        if _chord_names_on_line(line)
    ]
    groups = [names for _, names in indexed]
    if not _should_pair_lyric_chord_lines(groups):
        return None

    result: list[dict[str, Any]] = []
    cursor = 0
    while cursor < len(indexed):
        first_idx, first = indexed[cursor]
        second_idx, second = indexed[cursor + 1]
        pair = first + second
        line_start = first_idx
        line_end = second_idx + 1
        repeat = 1
        scan = cursor + 2
        while scan + 1 < len(indexed):
            left_idx, left = indexed[scan]
            right_idx, right = indexed[scan + 1]
            if left + right != pair:
                break
            repeat += 1
            line_end = right_idx + 1
            scan += 2
        result.append(
            {
                "chords": pair,
                "repeat": repeat,
                "line_start": line_start,
                "line_end": line_end,
            }
        )
        cursor = scan
    return result


def _compact_chord_rows_with_spans(
    chord_lines: list[list[dict[str, Any]]],
    chord_seq: list[str],
    progression_override: str | None = None,
    bar_texts: list[str] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Compact lyric chords plus optional bar rows; lyric rows include line_start/line_end."""
    bar_rows: list[dict[str, Any]] = []
    if bar_texts:
        for text in bar_texts:
            bar_rows.extend(_compact_from_bar_notation(text))

    line_count = len(chord_lines)
    full_span = {"line_start": 0, "line_end": line_count}

    if progression_override:
        lyric_rows = [
            {**row, **full_span}
            for row in progression_to_compact_rows(parse_progression_spec(progression_override))
        ]
        return lyric_rows, bar_rows

    if bar_rows and not chord_lines:
        return [], bar_rows

    paired = _compact_from_lyric_line_pairs_with_spans(chord_lines)
    if paired:
        return paired, bar_rows

    rows: list[list[str]] = [_chord_names_on_line(line) for line in chord_lines if line]

    if chord_seq:
        detected = detect_repeating_progression(chord_seq)
        if detected.get("source") == "detected":
            pattern = detected.get("pattern") or []
            repeats = detected.get("repeat") or 1
            consumed = len(pattern) * repeats
            lyric_rows: list[dict[str, Any]] = []
            if pattern:
                span = _line_span_for_chord_range(chord_lines, 0, consumed)
                lyric_rows.append(
                    {
                        "chords": pattern,
                        "repeat": repeats,
                        "line_start": span[0],
                        "line_end": span[1],
                    }
                )
            tail = detected.get("tail") or []
            if tail:
                span = _line_span_for_chord_range(chord_lines, consumed, len(chord_seq))
                lyric_rows.append(
                    {
                        "chords": tail,
                        "repeat": 1,
                        "line_start": span[0],
                        "line_end": span[1],
                    }
                )
            return lyric_rows, bar_rows

    sparse = _compact_sparse_lyric_progression(rows, chord_seq)
    if sparse:
        return [{**row, **full_span} for row in sparse], bar_rows

    if not rows and chord_seq:
        detected = detect_repeating_progression(chord_seq)
        lyric_rows = [
            {**row, **full_span} for row in progression_to_compact_rows(detected)
        ]
        return lyric_rows, bar_rows

    if not rows:
        return [], bar_rows

    alternating = _detect_alternating_pair_pattern(rows)
    if alternating:
        active = _active_chord_line_indices(chord_lines)
        lyric_rows = []
        for index, row in enumerate(alternating):
            if index * 2 + 1 < len(active):
                start = active[index * 2]
                end = active[min(index * 2 + 2, len(active) - 1)] + 1
            else:
                start, end = full_span["line_start"], full_span["line_end"]
            lyric_rows.append({**row, "line_start": start, "line_end": end})
        return lyric_rows, bar_rows

    indexed_rows = [
        (index, names)
        for index, line in enumerate(chord_lines)
        if (names := _chord_names_on_line(line))
    ]
    collapsed: list[tuple[list[str], int, int, int]] = []
    for line_index, row in indexed_rows:
        if collapsed and collapsed[-1][0] == row:
            collapsed[-1] = (
                row,
                collapsed[-1][1] + 1,
                collapsed[-1][2],
                line_index + 1,
            )
        else:
            collapsed.append((row, 1, line_index, line_index + 1))

    lyric_rows: list[dict[str, Any]] = []
    for row, count, line_start, line_end in collapsed:
        split_rows = _split_chord_row_for_display(row)
        for idx, split in enumerate(split_rows):
            repeat = count if idx == len(split_rows) - 1 else 1
            lyric_rows.append(
                {
                    "chords": split,
                    "repeat": repeat,
                    "line_start": line_start,
                    "line_end": line_end,
                }
            )
    return lyric_rows, bar_rows


def _append_cues_for_line_range(
    flow: list[dict[str, Any]],
    chord_lines: list[list[dict[str, Any]]],
    cue_line_start: int,
    cue_line_end: int,
    pattern_span_start: int,
    pattern_span_end: int,
    pattern: list[str],
    seen_notes: set[str],
) -> None:
    pattern_len = len(pattern)
    if not pattern_len:
        return
    for line_index in range(cue_line_start, cue_line_end):
        if line_index >= len(chord_lines):
            continue
        for chord_index, cue in _inline_cues_on_line(chord_lines[line_index]):
            global_index = _global_chord_index_in_span(
                chord_lines,
                line_index,
                chord_index,
                pattern_span_start,
                pattern_span_end,
            )
            pattern_index = global_index % pattern_len
            note = _structure_note_for_cue(pattern, pattern_index, cue)
            if note not in seen_notes:
                seen_notes.add(note)
                flow.append({"type": "note", "text": note})


def _append_structure_chord_row_to_flow(
    flow: list[dict[str, Any]],
    chord_lines: list[list[dict[str, Any]]],
    row: dict[str, Any],
) -> None:
    pattern = row.get("chords") or []
    repeat = row.get("repeat") or 1
    start = row.get("line_start", 0)
    end = row.get("line_end", len(chord_lines))
    line_count = max(end - start, 0)
    seen_notes: set[str] = set()

    lines_per_cycle = line_count // repeat if repeat and line_count % repeat == 0 else 0
    cue_cycles = (
        _cycles_with_inline_cues(chord_lines, start, end, lines_per_cycle)
        if lines_per_cycle
        else set()
    )
    split_cycles = repeat > 1 and lines_per_cycle > 0 and len(cue_cycles) >= 2

    if split_cycles:
        for cycle in range(repeat):
            cycle_start = start + cycle * lines_per_cycle
            cycle_end = cycle_start + lines_per_cycle
            _append_cues_for_line_range(
                flow,
                chord_lines,
                cycle_start,
                cycle_end,
                cycle_start,
                cycle_end,
                pattern,
                seen_notes,
            )
            flow.append({"type": "chords", "chords": pattern, "repeat": 1})
        return

    _append_cues_for_line_range(
        flow,
        chord_lines,
        start,
        end,
        start,
        end,
        pattern,
        seen_notes,
    )
    flow.append({"type": "chords", "chords": pattern, "repeat": repeat})


def _append_structure_chord_chunk(
    flow: list[dict[str, Any]],
    chord_lines: list[list[dict[str, Any]]],
    chord_seq: list[str],
    bar_texts: list[str] | None,
    progression_override: str | None,
) -> None:
    lyric_rows, bar_rows = _compact_chord_rows_with_spans(
        chord_lines,
        chord_seq,
        progression_override=progression_override,
        bar_texts=bar_texts,
    )
    for row in lyric_rows:
        _append_structure_chord_row_to_flow(flow, chord_lines, row)
    for row in bar_rows:
        flow.append(
            {
                "type": "chords",
                "chords": row["chords"],
                "repeat": row.get("repeat", 1),
            }
        )


def compact_chord_rows(
    chord_lines: list[list[dict[str, Any]]],
    chord_seq: list[str],
    progression_override: str | None = None,
    bar_texts: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Group chords into compact rows for structure view, collapsing repeated patterns."""
    lyric_rows, bar_rows = _compact_chord_rows_with_spans(
        chord_lines,
        chord_seq,
        progression_override=progression_override,
        bar_texts=bar_texts,
    )
    return [
        {"chords": row["chords"], "repeat": row.get("repeat", 1)} for row in lyric_rows
    ] + bar_rows


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
        _append_structure_chord_chunk(
            flow,
            chord_lines,
            chord_seq,
            bar_texts or None,
            progression_override,
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
