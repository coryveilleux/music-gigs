from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator

from fpdf import FPDF
from fpdf.enums import Align, XPos, YPos

from music_gigs.chordpro import _build_chord_line, section_display_title

MAIN_WIDTH_FRAC = 0.70
SIDEBAR_WIDTH_FRAC = 0.28
MIN_LAYOUT_SCALE = 0.62
MAX_SONG_PAGES = 2


@dataclass(frozen=True)
class GigPdfTheme:
    page_bg: tuple[int, int, int] = (255, 255, 255)
    text: tuple[int, int, int] = (17, 24, 39)
    muted: tuple[int, int, int] = (75, 85, 99)
    accent: tuple[int, int, int] = (180, 83, 9)
    harmony: tuple[int, int, int] = (29, 78, 216)
    note_fill: tuple[int, int, int] = (243, 244, 246)
    note_border: tuple[int, int, int] = (203, 213, 225)
    note_text: tuple[int, int, int] = (55, 65, 81)
    link: tuple[int, int, int] = (29, 78, 216)
    sidebar_fill: tuple[int, int, int] = (248, 250, 252)
    sidebar_border: tuple[int, int, int] = (203, 213, 225)


@dataclass(frozen=True)
class SongLayout:
    scale: float
    title: float = 14
    meta: float = 9
    section: float = 10
    lyric: float = 11
    chord: float = 9
    note: float = 9
    sidebar: float = 8

    @classmethod
    def from_scale(cls, scale: float) -> SongLayout:
        return cls(
            scale=scale,
            title=14 * scale,
            meta=9 * scale,
            section=10 * scale,
            lyric=11 * scale,
            chord=9 * scale,
            note=9 * scale,
            sidebar=8 * scale,
        )


DEFAULT_THEME = GigPdfTheme()
MONO = "Courier"
SANS = "Helvetica"
_SCALE_STEPS = (1.0, 0.95, 0.9, 0.85, 0.8, 0.75, 0.7, 0.65, 0.62)

_UNICODE_REPLACEMENTS = {
    "\u2019": "'",
    "\u2018": "'",
    "\u201c": '"',
    "\u201d": '"',
    "\u2013": "-",
    "\u2014": "-",
    "\u2026": "...",
}


def _pdf_text(value: str) -> str:
    text = value or ""
    for src, dst in _UNICODE_REPLACEMENTS.items():
        text = text.replace(src, dst)
    return text.encode("latin-1", "replace").decode("latin-1")


def _line_count(pdf: FPDF, width: float, line_height: float, text: str) -> int:
    if not text:
        return 0
    lines = pdf.multi_cell(width, line_height, _pdf_text(text), dry_run=True, output="LINES")
    return max(1, len(lines))


def _outline_label(entry: dict[str, Any]) -> str:
    return section_display_title(
        entry.get("type", ""),
        entry.get("label") or "",
        entry.get("number"),
    )


def _line_height_mm(font_pt: float, ratio: float = 0.48) -> float:
    """Minimum multi_cell row height for a font size in points (PDF unit is mm)."""
    return max(font_pt * ratio * 0.35, 3.4)


def _sidebar_chord_lines(entry: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for row in entry.get("chord_compact") or []:
        text = " ".join(row.get("chords") or [])
        repeat = row.get("repeat") or 1
        if repeat > 1:
            text = f"{text} (×{repeat})"
        if text:
            lines.append(text)
    if not lines and entry.get("chords"):
        lines.append(" ".join(entry["chords"][:16]))
    return lines


def _lyric_plain(block: dict[str, Any]) -> str:
    segments = block.get("segments")
    if segments:
        return "".join(segment.get("text", "") for segment in segments)
    return block.get("lyrics", "")


def _lyric_segments(block: dict[str, Any]) -> list[dict[str, Any]]:
    segments = block.get("segments")
    if segments:
        return segments
    text = block.get("lyrics", "")
    return [{"text": text, "harmony": False, "direction": False}] if text else []


def _group_blocks(blocks: list[dict[str, Any]]) -> list[tuple[str, Any]]:
    """PDF renders one lyric row at a time (no side-by-side pairs — page breaks break Y sync)."""
    return [("single", block) for block in blocks]


class GigBookPDF(FPDF):
    def __init__(self, theme: GigPdfTheme = DEFAULT_THEME) -> None:
        super().__init__(format="Letter", unit="mm")
        self.theme = theme
        self.set_auto_page_break(auto=True, margin=18)
        self.set_margins(left=12, top=14, right=12)

    @contextmanager
    def _frozen_cursor(self) -> Iterator[None]:
        """Draw in a sidebar/overlay without moving the main-column cursor."""
        saved_x, saved_y = self.get_x(), self.get_y()
        try:
            yield
        finally:
            self.set_xy(saved_x, saved_y)

    def content_width(self) -> float:
        return self.w - self.l_margin - self.r_margin

    def column_geometry(self) -> tuple[float, float, float, float]:
        total = self.content_width()
        main_w = total * MAIN_WIDTH_FRAC
        sidebar_w = total * SIDEBAR_WIDTH_FRAC
        gutter = total - main_w - sidebar_w
        main_x = self.l_margin
        sidebar_x = self.l_margin + main_w + gutter
        return main_x, main_w, sidebar_x, sidebar_w

    def lyric_column(self, song_first_page: int) -> tuple[float, float]:
        """First song page shares width with structure sidebar; later pages use full width."""
        if self.page_no() > song_first_page:
            return self.l_margin, self.content_width()
        main_x, main_w, _, _ = self.column_geometry()
        return main_x, main_w

    def song_body_top(self) -> float:
        return self.t_margin + 5

    def song_body_bottom(self) -> float:
        return self.h - 13

    def available_song_height(self) -> float:
        return self.song_body_bottom() - self.song_body_top()

    def header(self) -> None:
        self.set_font(SANS, "I", 8)
        self.set_text_color(*self.theme.muted)
        self.cell(0, 4, _pdf_text(f"Page {self.page_no()}"), align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(0.5)

    def footer(self) -> None:
        self.set_y(-11)
        self.set_font(SANS, "I", 8)
        self.set_text_color(*self.theme.muted)
        self.cell(0, 5, _pdf_text(f"Page {self.page_no()}"), align="C")

    def _text_height(
        self,
        text: str,
        width: float,
        line_height: float,
        family: str,
        style: str,
        size: float,
    ) -> float:
        self.set_font(family, style=style, size=size)
        return _line_count(self, width, line_height, text) * line_height

    def _tight_lyric_height(
        self, block: dict[str, Any], width: float, layout: SongLayout, song_key: str
    ) -> float:
        lyric = _lyric_plain(block)
        chords = block.get("chords") or []
        height = 0.0
        chord_h = _line_height_mm(layout.chord)
        lyric_h = _line_height_mm(layout.lyric)
        if chords:
            height += chord_h + 0.25
        height += self._text_height(lyric, width, lyric_h, MONO, "", layout.lyric)
        return height + 0.5

    def estimate_block_height(
        self, item: tuple[str, Any], layout: SongLayout, song_key: str, main_w: float
    ) -> float:
        block = item[1]
        block_kind = block.get("kind")
        if block_kind in {"note", "harmony"}:
            text = block.get("text", "")
            return 2 + self._text_height(text, main_w - 2, layout.note * 0.46, SANS, "I", layout.note) + 2.5
        if block_kind in {"bars", "chord_line"}:
            text = block.get("text", "")
            if block_kind == "chord_line":
                text = "  ".join(
                    entry.get("chord", "") for entry in block.get("chords", []) if entry.get("chord")
                )
            return self._text_height(text, main_w, _line_height_mm(layout.chord), MONO, "B", layout.chord) + 1
        if block_kind == "lyric":
            return self._tight_lyric_height(block, main_w, layout, song_key) + 0.3
        if block_kind in {"tab", "abc"}:
            return 12
        return 0.0

    def estimate_song_height(self, song: dict[str, Any], layout: SongLayout) -> float:
        main_x, main_w, _, _ = self.column_geometry()
        height = layout.title * 0.42 + 0.5
        meta_parts = [f"Set {song['set']}"]
        if song.get("artist"):
            meta_parts.append(song["artist"])
        if song.get("key"):
            meta_parts.append(f"Key: {song['key']}")
        height += self._text_height(
            " · ".join(meta_parts), main_w, layout.meta * 0.48, SANS, "", layout.meta
        )
        height += 1.5
        song_key = song.get("key") or "C"
        chart_sections = 0
        for section in song.get("sections") or []:
            if section.get("type") == "comment":
                for block in section.get("blocks") or []:
                    if block.get("kind") == "note":
                        height += self.estimate_block_height(("single", block), layout, song_key, main_w)
                continue
            if chart_sections:
                height += 1.35
            chart_sections += 1
            label = section_display_title(
                section.get("type", ""),
                section.get("label") or "",
                section.get("number"),
            )
            height += layout.section * 0.48 + 0.3
            height += self._text_height(label, main_w, layout.section * 0.48, SANS, "B", layout.section)
            grouped = _group_blocks(section.get("blocks") or [])
            for item in grouped:
                height += self.estimate_block_height(item, layout, song_key, main_w)
            height += 0.5
        return height

    def choose_song_layout(self, song: dict[str, Any]) -> SongLayout:
        single_page = self.available_song_height()
        multi_budget = single_page * MAX_SONG_PAGES - 12
        for step in _SCALE_STEPS:
            if step < MIN_LAYOUT_SCALE:
                continue
            layout = SongLayout.from_scale(step)
            if self.estimate_song_height(song, layout) <= single_page:
                return layout
        for step in _SCALE_STEPS:
            if step < MIN_LAYOUT_SCALE:
                continue
            layout = SongLayout.from_scale(step)
            if self.estimate_song_height(song, layout) <= multi_budget:
                return layout
        return SongLayout.from_scale(MIN_LAYOUT_SCALE)

    def draw_section_divider(self, x: float, width: float) -> None:
        y = self.get_y() + 0.35
        self.set_draw_color(*self.theme.note_border)
        self.set_line_width(0.12)
        self.line(x, y, x + width, y)
        self.ln(1.0)

    def _render_styled_mono_line(
        self,
        x: float,
        y: float,
        line_w: float,
        lyric_h: float,
        segments: list[dict[str, Any]],
        lyric_size: float,
    ) -> None:
        """Paint lyrics segment-by-segment (harmony color) without shifting columns."""
        margin = self.c_margin
        # One left inset to match the chord row; zero margin between segment cells.
        self.c_margin = 0
        self.set_xy(x + margin, y)
        try:
            for segment in segments:
                text = segment.get("text", "")
                if not text:
                    continue
                self.set_font(MONO, size=lyric_size)
                if segment.get("harmony"):
                    self.set_text_color(*self.theme.harmony)
                else:
                    self.set_text_color(*self.theme.text)
                seg_w = self.get_string_width(_pdf_text(text))
                self.cell(
                    seg_w,
                    lyric_h,
                    _pdf_text(text),
                    new_x=XPos.RIGHT,
                    new_y=YPos.TOP,
                )
        finally:
            self.c_margin = margin
        self.set_xy(x, y + lyric_h)

    def draw_info_box(self, text: str, layout: SongLayout, width: float, x: float) -> None:
        if not text.strip():
            return
        y0 = self.get_y()
        self.set_xy(x, y0)
        line_h = _line_height_mm(layout.note, ratio=0.46)
        self.set_fill_color(*self.theme.note_fill)
        self.set_draw_color(*self.theme.note_border)
        self.set_font(SANS, "I", size=layout.note)
        self.set_text_color(*self.theme.note_text)
        self.multi_cell(
            width,
            line_h,
            _pdf_text(text),
            border=1,
            fill=True,
            new_x=XPos.LEFT,
            new_y=YPos.NEXT,
        )
        self.ln(0.5)

    def _lyric_text_width(self, text: str, size: float) -> float:
        self.set_font(MONO, size=size)
        return self.get_string_width(_pdf_text(text))

    def _lyric_inner_max_width(self, column_width: float) -> float:
        return max(10.0, column_width - 2 * self.c_margin)

    def _fit_mono_line_font_size(
        self, lines: list[str], column_width: float, base_size: float
    ) -> float:
        inner_max = self._lyric_inner_max_width(column_width)
        size = base_size
        while size > 7:
            if all(self._lyric_text_width(line, size) <= inner_max for line in lines if line):
                return size
            size -= 0.5
        return size

    def render_tight_lyric(
        self,
        block: dict[str, Any],
        x: float,
        width: float,
        layout: SongLayout,
        song_key: str,
    ) -> float:
        """Match HTML: monospace chord row (_build_chord_line) then lyric, same font."""
        y0 = self.get_y()
        lyric = _lyric_plain(block)
        chords = block.get("chords") or []
        lyric_h = _line_height_mm(layout.lyric)
        segments = _lyric_segments(block)
        if not chords:
            lyric_size = self._fit_mono_line_font_size([lyric], width, layout.lyric)
            lyric_h = _line_height_mm(lyric_size)
            self.set_xy(x, y0)
            self._render_styled_mono_line(x, y0, width, lyric_h, segments, lyric_size)
            return self.get_y() - y0

        key = song_key or "C"
        lyric_size = self._fit_mono_line_font_size([lyric], width, layout.lyric)
        chord_line = _build_chord_line(lyric, chords, key).rstrip()
        lyric_size = self._fit_mono_line_font_size([lyric, chord_line], width, lyric_size)
        chord_line = _build_chord_line(lyric, chords, key).rstrip()
        chord_h = _line_height_mm(lyric_size)
        lyric_h = _line_height_mm(lyric_size)
        line_w = (
            max(
                self._lyric_text_width(chord_line, lyric_size),
                self._lyric_text_width(lyric, lyric_size),
            )
            + 2 * self.c_margin
        )

        self.set_xy(x, y0)
        self.set_font(MONO, size=lyric_size)
        self.set_text_color(*self.theme.accent)
        self.cell(
            line_w,
            chord_h,
            _pdf_text(chord_line),
            align=Align.L,
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )
        y_lyric = self.get_y() + 0.15
        self._render_styled_mono_line(
            x, y_lyric, line_w, lyric_h, segments, lyric_size
        )
        return self.get_y() - y0

    def render_song_structure_sidebar(
        self,
        song: dict[str, Any],
        layout: SongLayout,
        x: float,
        y: float,
        width: float,
    ) -> None:
        """Full structure + chords on the first song page only (not tied to lyric flow)."""
        outlines = song.get("outline") or []
        structure = (song.get("structure") or "").strip()
        if not structure and not outlines:
            return

        line_h = _line_height_mm(layout.sidebar, ratio=0.46)
        blocks: list[str] = []
        if structure:
            blocks.append(f"Form: {structure}")
        for entry in outlines:
            section_lines = [_outline_label(entry)] + _sidebar_chord_lines(entry)
            blocks.append("\n".join(section_lines))
        body = "\n\n".join(blocks)
        height = self._text_height(body, width - 2.4, line_h, MONO, "", layout.sidebar) + 3

        self.set_fill_color(*self.theme.sidebar_fill)
        self.set_draw_color(*self.theme.sidebar_border)
        self.rect(x, y, width, height, style="DF")
        cursor_y = y + 1.2
        if structure:
            self.set_xy(x + 1.2, cursor_y)
            self.set_font(SANS, "B", size=layout.sidebar)
            self.set_text_color(*self.theme.text)
            self.multi_cell(
                width - 2.4,
                line_h,
                _pdf_text(f"Form: {structure}"),
                new_x=XPos.LEFT,
                new_y=YPos.NEXT,
            )
            cursor_y = self.get_y() + 1
        for entry in outlines:
            self.set_xy(x + 1.2, cursor_y)
            self.set_font(SANS, "B", size=layout.sidebar)
            self.set_text_color(*self.theme.accent)
            self.multi_cell(
                width - 2.4,
                line_h,
                _pdf_text(_outline_label(entry)),
                new_x=XPos.LEFT,
                new_y=YPos.NEXT,
            )
            chord_lines = _sidebar_chord_lines(entry)
            if chord_lines:
                self.set_x(x + 1.2)
                self.set_font(MONO, size=layout.sidebar)
                self.set_text_color(*self.theme.text)
                self.multi_cell(
                    width - 2.4,
                    line_h,
                    _pdf_text("\n".join(chord_lines)),
                    new_x=XPos.LEFT,
                    new_y=YPos.NEXT,
                )
            cursor_y = self.get_y() + 1.5

    def render_song(self, song: dict[str, Any], layout: SongLayout | None = None) -> None:
        layout = layout or self.choose_song_layout(song)
        _, _, sidebar_x, sidebar_w = self.column_geometry()
        song_key = song.get("key") or "C"
        song_first_page = self.page_no()

        full_w = self.content_width()
        self.set_y(self.song_body_top())
        self.set_font(SANS, "B", size=layout.title)
        self.set_text_color(*self.theme.text)
        self.set_x(self.l_margin)
        self.multi_cell(
            full_w,
            layout.title * 0.42,
            _pdf_text(f"{song['number']}. {song['title']}"),
            new_x="LMARGIN",
            new_y="NEXT",
        )
        meta_parts = [f"Set {song['set']}"]
        if song.get("artist"):
            meta_parts.append(song["artist"])
        if song.get("key"):
            meta_parts.append(f"Key: {song['key']}")
        main_x, main_w = self.lyric_column(song_first_page)
        self.set_font(SANS, size=layout.meta)
        self.set_text_color(*self.theme.muted)
        self.set_x(main_x)
        self.multi_cell(
            main_w,
            layout.meta * 0.48,
            _pdf_text(" · ".join(meta_parts)),
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )

        structure_y = self.get_y() + 0.5
        with self._frozen_cursor():
            self.render_song_structure_sidebar(song, layout, sidebar_x, structure_y, sidebar_w)

        self.ln(0.6)

        chart_section_started = False
        for section in song.get("sections") or []:
            main_x, main_w = self.lyric_column(song_first_page)
            if section.get("type") == "comment":
                for block in section.get("blocks") or []:
                    if block.get("kind") == "note":
                        self.draw_info_box(block.get("text", ""), layout, main_w, main_x)
                continue

            if chart_section_started:
                self.draw_section_divider(main_x, main_w)
            chart_section_started = True

            label = section_display_title(
                section.get("type", ""),
                section.get("label") or "",
                section.get("number"),
            )
            self.set_x(main_x)
            self.set_font(SANS, "B", size=layout.section)
            self.set_text_color(*self.theme.accent)
            self.multi_cell(
                main_w,
                layout.section * 0.48,
                _pdf_text(label),
                new_x=XPos.LMARGIN,
                new_y=YPos.NEXT,
            )
            self.ln(0.15)

            for item in _group_blocks(section.get("blocks") or []):
                main_x, main_w = self.lyric_column(song_first_page)
                block = item[1]
                kind = block.get("kind")
                if kind in {"note", "harmony"}:
                    self.draw_info_box(block.get("text", ""), layout, main_w, main_x)
                elif kind in {"bars", "chord_line"}:
                    text = block.get("text", "")
                    if kind == "chord_line":
                        text = "  ".join(
                            entry.get("chord", "")
                            for entry in block.get("chords", [])
                            if entry.get("chord")
                        )
                    self.set_x(main_x)
                    self.set_font(MONO, "B", size=layout.chord)
                    self.set_text_color(*self.theme.accent)
                    self.multi_cell(
                        main_w,
                        _line_height_mm(layout.chord),
                        _pdf_text(text),
                        new_x=XPos.LMARGIN,
                        new_y=YPos.NEXT,
                    )
                    self.ln(0.15)
                elif kind == "lyric":
                    self.render_tight_lyric(block, main_x, main_w, layout, song_key)
                    self.ln(0.1)
                elif kind in {"tab", "abc"}:
                    label_text = block.get("label") or kind
                    body = (block.get("text") or "").strip()
                    preview = "\n".join(body.splitlines()[:6])
                    self.draw_info_box(f"{label_text}\n{preview}", layout, main_w, main_x)

            self.ln(0.15)

    def render_setlist(
        self,
        gig_data: dict[str, Any],
        songs: list[dict[str, Any]],
        song_start_pages: dict[str, int],
    ) -> None:
        self.set_fill_color(*self.theme.page_bg)
        self.rect(0, 0, self.w, self.h, style="F")

        self.set_font(SANS, "B", size=18)
        self.set_text_color(*self.theme.text)
        self.cell(0, 8, _pdf_text(gig_data.get("band", "")), new_x="LMARGIN", new_y="NEXT")
        meta = " · ".join(
            part
            for part in [gig_data.get("gig"), gig_data.get("date"), gig_data.get("venue")]
            if part
        )
        self.set_font(SANS, size=11)
        self.set_text_color(*self.theme.muted)
        self.multi_cell(0, 5, _pdf_text(meta), new_x="LMARGIN", new_y="NEXT")
        self.ln(3)

        self.set_font(SANS, "B", size=11)
        self.set_text_color(*self.theme.text)
        self.cell(0, 6, "Set list", new_x="LMARGIN", new_y="NEXT")
        self.ln(1)

        col_num = 10
        col_page = 14
        col_key = 16
        col_title = self.w - self.l_margin - self.r_margin - col_num - col_page - col_key

        def header_row() -> None:
            self.set_font(SANS, "B", size=9)
            self.set_text_color(*self.theme.muted)
            self.cell(col_num, 5, "#", border="B")
            self.cell(col_title, 5, "Song", border="B")
            self.cell(col_key, 5, "Key", border="B", align="C")
            self.cell(col_page, 5, "Page", border="B", align="C")
            self.ln(5)

        songs_by_set: dict[int, list[dict[str, Any]]] = {}
        for song in songs:
            songs_by_set.setdefault(song["set"], []).append(song)

        for set_info in gig_data.get("sets") or []:
            set_number = set_info["number"]
            set_songs = songs_by_set.get(set_number, [])
            if not set_songs:
                continue
            self.ln(2)
            self.set_font(SANS, "B", size=11)
            self.set_text_color(*self.theme.accent)
            self.cell(0, 6, _pdf_text(f"Set {set_number}"), new_x="LMARGIN", new_y="NEXT")
            header_row()
            for song in set_songs:
                page = song_start_pages.get(song["slug"])
                self.set_font(SANS, size=10)
                self.set_text_color(*self.theme.text)
                self.cell(col_num, 5, str(song["number"]))
                link = self.add_link(page=page) if page else None
                if link:
                    self.set_text_color(*self.theme.link)
                self.cell(col_title, 5, _pdf_text(song["title"]), link=link)
                self.set_text_color(*self.theme.text)
                self.cell(col_key, 5, _pdf_text(song.get("key") or ""), align="C")
                page_text = str(page) if page else "-"
                if page:
                    page_link = self.add_link(page=page)
                    self.set_text_color(*self.theme.link)
                    self.cell(col_page, 5, page_text, align="C", link=page_link)
                else:
                    self.cell(col_page, 5, page_text, align="C")
                self.ln(5)


def render_gig_pdf(
    gig_data: dict[str, Any],
    *,
    song_limit: int | None = None,
    theme: GigPdfTheme = DEFAULT_THEME,
) -> bytes:
    all_songs = gig_data.get("songs") or []
    songs = all_songs[:song_limit] if song_limit else all_songs

    planner = GigBookPDF(theme=theme)
    planner.add_page()
    layouts = {song["slug"]: planner.choose_song_layout(song) for song in songs}
    song_start_pages = {song["slug"]: index + 2 for index, song in enumerate(songs)}

    pdf = GigBookPDF(theme=theme)
    pdf.add_page()
    pdf.render_setlist(gig_data, songs, song_start_pages)

    for song in songs:
        pdf.add_page()
        pdf.set_auto_page_break(auto=True, margin=14)
        layout = layouts[song["slug"]]
        pdf.render_song(song, layout=layout)

    return bytes(pdf.output())
