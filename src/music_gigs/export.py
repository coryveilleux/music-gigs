from __future__ import annotations

import csv
import io
import math
from typing import TYPE_CHECKING

from fpdf import FPDF

from music_gigs.loader import format_duration
from music_gigs.models import DEFAULT_TEXT_TEMPLATE, SetList

if TYPE_CHECKING:
    from music_gigs.models import Band, Song


def catalog_songs_sorted(band: Band, *, active_only: bool = True) -> list[Song]:
    songs = [s for s in band.catalog.songs if s.active or not active_only]
    return sorted(
        songs,
        key=lambda s: (
            band.member_name(s.lead_singer).lower(),
            s.title.lower(),
        ),
    )


def _format_key_for_pdf(key: str) -> str:
    formatted = key.replace("(mixolydian)", "mixo").replace("mixolydian", "mixo")
    return " ".join(formatted.split())


def _catalog_review_rows(
    band: Band,
    *,
    active_only: bool = True,
    first_name_only: bool = False,
    pdf_keys: bool = False,
) -> list[tuple[str, str, str, str]]:
    songs = catalog_songs_sorted(band, active_only=active_only)
    rows: list[tuple[str, str, str, str]] = []
    for song in songs:
        singer = (
            band.member_first_name(song.lead_singer)
            if first_name_only
            else band.member_name(song.lead_singer)
        )
        key = _format_key_for_pdf(song.key) if pdf_keys else song.key
        rows.append((singer, key, song.title, song.original_artist))
    return rows


def _align_catalog_rows(rows: list[tuple[str, str, str, str]]) -> list[str]:
    if not rows:
        return []
    max_singer = max(len(singer) for singer, _, _, _ in rows)
    max_key = max(len(key) for _, key, _, _ in rows)
    return [
        f"{singer:<{max_singer}} - {key:<{max_key}} - {title}: {artist}"
        for singer, key, title, artist in rows
    ]


def catalog_review_lines(band: Band, *, active_only: bool = True) -> list[str]:
    """Aligned catalog lines: singer - key - title: artist."""
    return _align_catalog_rows(_catalog_review_rows(band, active_only=active_only))


def catalog_pdf_lines_per_page(song_count: int) -> int:
    """Lines per page for PDF; fewer lines leaves room for larger type."""
    if song_count <= 0:
        return 1
    if song_count <= 12:
        return song_count
    if song_count <= 24:
        return math.ceil(song_count / 2)
    for lines in range(12, 8, -1):
        if math.ceil(song_count / lines) <= 4:
            return lines
    return 10


def _pdf_font_size_for_lines(
    pdf: FPDF,
    lines: list[str],
    lines_per_page: int,
) -> tuple[float, float]:
    """Pick font size and line height to fill the page without clipping."""
    page_height_mm = 215.9
    page_width_mm = 279.4
    margin_v = 10
    header_mm = 11
    margin_h = 14
    usable_height = page_height_mm - (2 * margin_v) - header_mm
    usable_width = page_width_mm - (2 * margin_h)
    line_height = usable_height / lines_per_page
    font_size = min(line_height / 0.5, 22)

    while font_size >= 10:
        pdf.set_font("Courier", size=font_size)
        widest = max(pdf.get_string_width(line) for line in lines)
        if widest <= usable_width:
            return font_size, line_height
        font_size -= 0.5

    pdf.set_font("Courier", size=10)
    return 10.0, line_height


def catalog_pdf_layout(song_count: int) -> tuple[int, int]:
    """Return (lines_per_page, font_size_pt) — font size is a legacy estimate."""
    lines = catalog_pdf_lines_per_page(song_count)
    if song_count <= 12:
        return lines, 18
    if song_count <= 24:
        return lines, 16
    pages = math.ceil(song_count / lines) if lines else 1
    return lines, 18 if pages <= 3 else 16


def render_catalog_review(band: Band, *, active_only: bool = True) -> str:
    """Aligned catalog list: singer - key - title: artist (one per line)."""
    lines = catalog_review_lines(band, active_only=active_only)
    if not lines:
        return ""
    return "\n".join(lines) + "\n"


def render_catalog_review_pdf(band: Band, *, active_only: bool = True) -> bytes:
    """PDF catalog list sized for printing and reading at arm's length."""
    lines = _align_catalog_rows(
        _catalog_review_rows(band, active_only=active_only, first_name_only=True, pdf_keys=True)
    )
    if not lines:
        return b""

    lines_per_page = catalog_pdf_lines_per_page(len(lines))
    total_pages = math.ceil(len(lines) / lines_per_page)

    pdf = FPDF(orientation="L", unit="mm", format="letter")
    pdf.set_auto_page_break(auto=False)
    pdf.set_margins(left=14, top=10, right=14)

    sample_page = lines[:lines_per_page]
    font_size, line_height = _pdf_font_size_for_lines(pdf, sample_page, lines_per_page)
    header_height = font_size * 0.7

    for page_index in range(total_pages):
        page_lines = lines[page_index * lines_per_page : (page_index + 1) * lines_per_page]
        pdf.add_page()
        pdf.set_font("Courier", style="B", size=font_size + 1)
        pdf.cell(
            0,
            header_height,
            f"{band.name}  ({page_index + 1}/{total_pages})",
            new_x="LMARGIN",
            new_y="NEXT",
            align="C",
        )
        pdf.set_font("Courier", size=font_size)
        for line in page_lines:
            pdf.cell(0, line_height, line, new_x="LMARGIN", new_y="NEXT")

    return bytes(pdf.output())


def _song_field_values(band: Band, entry) -> dict[str, str]:
    song = entry.song
    return {
        "set_number": str(entry.set_number),
        "lead_singer": band.member_name(song.lead_singer),
        "key": song.key,
        "title": song.title,
        "original_artist": song.original_artist,
        "duration": format_duration(song.duration_seconds),
        "notes": (song.notes or "").replace("\n", " ").strip(),
    }


def render_text(
    band: Band,
    setlist: SetList,
    columns: list[str] | None = None,
    template: str = DEFAULT_TEXT_TEMPLATE,
) -> str:
    lines: list[str] = []
    sets = setlist.sets

    for set_number in sorted(sets):
        lines.append(f"Set {set_number}")
        lines.append("-" * 6)
        for entry in sets[set_number]:
            values = _song_field_values(band, entry)
            if columns:
                line = " - ".join(values[col] for col in columns if col in values and col != "set_number")
            else:
                line = template.format(**values)
            lines.append(line)
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def render_csv(
    band: Band,
    setlist: SetList,
    columns: list[str],
) -> str:
    output = io.StringIO()
    labels = {
        "set_number": "Set",
        "lead_singer": "Lead Singer",
        "key": "Key",
        "title": "Title",
        "original_artist": "Original Artist",
        "duration": "Duration",
        "notes": "Notes",
    }
    writer = csv.writer(output)
    writer.writerow([labels.get(col, col) for col in columns])

    for entry in setlist.songs:
        values = _song_field_values(band, entry)
        writer.writerow([values.get(col, "") for col in columns])

    return output.getvalue()
