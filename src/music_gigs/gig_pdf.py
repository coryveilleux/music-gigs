from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator

from fpdf import FPDF
from fpdf.enums import Align, XPos, YPos

from music_gigs.chordpro import _build_chord_line, section_display_title

MAIN_WIDTH_FRAC = 0.70
SIDEBAR_WIDTH_FRAC = 0.28
MIN_LAYOUT_SCALE = 0.38
MAX_SONG_PAGES = 1
MIN_LYRIC_FONT_PT = 5.0
NAV_BAR_HEIGHT_MM = 11.0
FOOTER_RESERVE_MM = 18.0
SETLIST_PAGE = 1


@dataclass(frozen=True)
class PageNav:
    setlist_page: int = SETLIST_PAGE
    prev_page: int | None = None
    next_page: int | None = None


def build_page_nav(
    songs: list[dict[str, Any]], song_start_pages: dict[str, int]
) -> dict[int, PageNav]:
    """Per-page prev / set list / next targets (one page per song)."""
    song_pages = [song_start_pages[song["slug"]] for song in songs]
    nav: dict[int, PageNav] = {
        SETLIST_PAGE: PageNav(
            prev_page=None,
            next_page=song_pages[0] if song_pages else None,
        )
    }
    for index, page in enumerate(song_pages):
        nav[page] = PageNav(
            prev_page=song_pages[index - 1] if index > 0 else SETLIST_PAGE,
            next_page=song_pages[index + 1] if index + 1 < len(song_pages) else None,
        )
    return nav


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
    nav_fill: tuple[int, int, int] = (248, 250, 252)
    nav_border: tuple[int, int, int] = (203, 213, 225)
    nav_disabled: tuple[int, int, int] = (156, 163, 175)
    on_accent: tuple[int, int, int] = (255, 255, 255)


@dataclass(frozen=True)
class SongLayout:
    scale: float
    columns: int = 1
    title: float = 14
    meta: float = 9
    section: float = 10
    lyric: float = 11
    chord: float = 9
    note: float = 9
    sidebar: float = 8

    @classmethod
    def from_scale(cls, scale: float, *, columns: int = 1) -> SongLayout:
        return cls(
            scale=scale,
            columns=columns,
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
_SCALE_STEPS = (
    1.0,
    0.95,
    0.9,
    0.85,
    0.8,
    0.75,
    0.7,
    0.65,
    0.62,
    0.58,
    0.55,
    0.52,
    0.48,
    0.45,
    0.42,
    0.4,
    0.38,
)

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
        self._single_song_page = False
        self._page_nav_by_page: dict[int, PageNav] = {}
        self.set_margins(left=12, top=14, right=12)
        self.set_auto_page_break(auto=True, margin=FOOTER_RESERVE_MM)

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
        return self.h - FOOTER_RESERVE_MM

    def available_song_height(self) -> float:
        return self.song_body_bottom() - self.song_body_top()

    def header(self) -> None:
        self.set_font(SANS, "I", 8)
        self.set_text_color(*self.theme.muted)
        self.cell(0, 4, _pdf_text(f"Page {self.page_no()}"), align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(0.5)

    def _draw_nav_button(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        label: str,
        target_page: int | None,
        *,
        primary: bool = False,
    ) -> None:
        self.set_draw_color(*self.theme.nav_border)
        self.set_line_width(0.2)
        if primary and target_page is not None:
            self.set_fill_color(*self.theme.accent)
            text_color = self.theme.on_accent
        elif target_page is not None:
            self.set_fill_color(*self.theme.nav_fill)
            text_color = self.theme.link
        else:
            self.set_fill_color(*self.theme.note_fill)
            text_color = self.theme.nav_disabled
        self.set_xy(x, y)
        self.set_font(SANS, "B" if target_page else "", 11)
        self.set_text_color(*text_color)
        link = self.add_link(page=target_page) if target_page is not None else None
        self.cell(
            width,
            height,
            _pdf_text(label),
            border=1,
            fill=True,
            align=Align.C,
            link=link,
        )

    def _render_footer_nav(self, nav: PageNav) -> None:
        gap = 1.2
        bar_h = NAV_BAR_HEIGHT_MM
        y0 = self.h - bar_h - 3
        x0 = self.l_margin
        total_w = self.content_width()
        btn_w = (total_w - 2 * gap) / 3
        self._draw_nav_button(
            x0,
            y0,
            btn_w,
            bar_h,
            "Prev",
            nav.prev_page,
        )
        self._draw_nav_button(
            x0 + btn_w + gap,
            y0,
            btn_w,
            bar_h,
            "Set list",
            nav.setlist_page,
            primary=True,
        )
        self._draw_nav_button(
            x0 + 2 * (btn_w + gap),
            y0,
            btn_w,
            bar_h,
            "Next",
            nav.next_page,
        )
        self.set_font(SANS, "I", 7)
        self.set_text_color(*self.theme.muted)
        page_label = _pdf_text(f"p.{self.page_no()}")
        label_w = self.get_string_width(page_label) + 2
        self.set_xy(self.w - self.r_margin - label_w, y0 - 3.2)
        self.cell(label_w, 3, page_label, align=Align.R)

    def footer(self) -> None:
        nav = self._page_nav_by_page.get(self.page_no())
        if nav:
            self._render_footer_nav(nav)
            return
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
        segments = _lyric_segments(block)
        song_key_val = song_key or "C"
        if chords:
            chord_line = _build_chord_line(lyric, chords, song_key_val).rstrip()
            lyric_size = self._fit_mono_line_font_size(
                [lyric, chord_line], width, layout.lyric
            )
        else:
            lyric_size = self._fit_mono_line_font_size([lyric], width, layout.lyric)
        lyric_h = _line_height_mm(lyric_size)
        rows = self._count_wrapped_segment_rows(segments, width, lyric_size)
        height = rows * lyric_h
        if chords:
            chord_h = _line_height_mm(lyric_size)
            height += chord_h + 0.4
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

    def estimate_section_height(
        self,
        section: dict[str, Any],
        layout: SongLayout,
        song_key: str,
        main_w: float,
        *,
        include_divider: bool,
    ) -> float:
        height = 0.0
        if include_divider:
            height += 1.35
        height += layout.section * 0.48 + 0.3
        label = section_display_title(
            section.get("type", ""),
            section.get("label") or "",
            section.get("number"),
        )
        height += self._text_height(
            label, main_w, layout.section * 0.48, SANS, "B", layout.section
        )
        height += 0.15
        for item in _group_blocks(section.get("blocks") or []):
            height += self.estimate_block_height(item, layout, song_key, main_w)
            if item[1].get("kind") == "lyric":
                height += 0.1
        height += 0.3
        return height

    def _chart_sections(self, song: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            section
            for section in song.get("sections") or []
            if section.get("type") != "comment"
        ]

    def _partition_sections_two_column(
        self,
        sections: list[dict[str, Any]],
        layout: SongLayout,
        song_key: str,
        column_width: float,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        if len(sections) < 2:
            return sections, []
        heights = [
            self.estimate_section_height(
                section, layout, song_key, column_width, include_divider=index > 0
            )
            for index, section in enumerate(sections)
        ]
        total = sum(heights)
        target = total / 2
        left: list[dict[str, Any]] = []
        right: list[dict[str, Any]] = []
        left_h = 0.0
        for section, height in zip(sections, heights):
            if not right and left_h + height <= target:
                left.append(section)
                left_h += height
            else:
                right.append(section)
        if not left:
            left = [sections[0]]
            right = sections[1:]
        return left, right

    def _render_chart_section(
        self,
        section: dict[str, Any],
        layout: SongLayout,
        song_key: str,
        main_x: float,
        main_w: float,
        song_first_page: int,
        *,
        chart_section_started: bool,
    ) -> bool:
        if chart_section_started:
            self.draw_section_divider(main_x, main_w)

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
            new_x=XPos.LEFT,
            new_y=YPos.NEXT,
        )
        self._advance_in_column(main_x, 0.15)

        for item in _group_blocks(section.get("blocks") or []):
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
                    new_x=XPos.LEFT,
                    new_y=YPos.NEXT,
                )
                self._advance_in_column(main_x, 0.15)
            elif kind == "lyric":
                self.render_tight_lyric(
                    block, main_x, main_w, layout, song_key, song_first_page
                )
                self._advance_in_column(main_x, 0.1)
            elif kind in {"tab", "abc"}:
                label_text = block.get("label") or kind
                body = (block.get("text") or "").strip()
                preview = "\n".join(body.splitlines()[:6])
                self.draw_info_box(f"{label_text}\n{preview}", layout, main_w, main_x)

        self._advance_in_column(main_x, 0.15)
        return True

    def _render_chart_column(
        self,
        sections: list[dict[str, Any]],
        layout: SongLayout,
        song_key: str,
        column_x: float,
        column_w: float,
        y_start: float,
        song_first_page: int,
    ) -> float:
        self.set_xy(column_x, y_start)
        started = False
        for section in sections:
            started = self._render_chart_section(
                section,
                layout,
                song_key,
                column_x,
                column_w,
                song_first_page,
                chart_section_started=started,
            )
        return self.get_y()

    def measure_rendered_song_height(
        self, song: dict[str, Any], layout: SongLayout
    ) -> tuple[float, int]:
        probe = GigBookPDF(theme=self.theme)
        probe.add_page()
        probe._single_song_page = True
        probe.set_auto_page_break(False)
        body_top = probe.song_body_top()
        probe.render_song(song, layout=layout)
        return probe.get_y() - body_top, probe.page_no()

    def choose_song_layout(self, song: dict[str, Any]) -> SongLayout:
        budget = self.available_song_height()
        chosen = SongLayout.from_scale(MIN_LAYOUT_SCALE, columns=2)
        for columns in (1, 2):
            for step in _SCALE_STEPS:
                if step < MIN_LAYOUT_SCALE:
                    continue
                layout = SongLayout.from_scale(step, columns=columns)
                used, pages = self.measure_rendered_song_height(song, layout)
                if pages == 1 and used <= budget:
                    return layout
                chosen = layout
        return chosen

    def draw_section_divider(self, x: float, width: float) -> None:
        y = self.get_y() + 0.35
        self.set_draw_color(*self.theme.note_border)
        self.set_line_width(0.12)
        self.line(x, y, x + width, y)
        self.set_xy(x, y + 1.0)

    def _split_mono_text(self, text: str, max_width: float, size: float) -> list[str]:
        if not text:
            return []
        if self._lyric_text_width(text, size) <= max_width:
            return [text]
        lines: list[str] = []
        current = ""
        for char in text:
            trial = current + char
            if self._lyric_text_width(trial, size) <= max_width:
                current = trial
            else:
                if current:
                    lines.append(current)
                current = char
        if current:
            lines.append(current)
        return lines

    def _count_wrapped_segment_rows(
        self,
        segments: list[dict[str, Any]],
        column_width: float,
        lyric_size: float,
    ) -> int:
        inner = self._lyric_inner_max_width(column_width)
        rows = 0
        row_width = 0.0
        for segment in segments:
            for piece in self._split_mono_text(segment.get("text", ""), inner, lyric_size):
                piece_w = self._lyric_text_width(piece, lyric_size)
                if row_width + piece_w > inner and row_width > 0:
                    rows += 1
                    row_width = 0.0
                row_width += piece_w
        if row_width > 0:
            rows += 1
        return max(1, rows)

    def _render_styled_mono_line(
        self,
        x: float,
        y: float,
        line_w: float,
        lyric_h: float,
        segments: list[dict[str, Any]],
        lyric_size: float,
    ) -> float:
        """Paint lyrics in-column; wrap to additional rows instead of bleeding sideways."""
        margin = self.c_margin
        self.c_margin = 0
        inner = max(8.0, line_w - 2 * margin)
        cur_y = y
        row_width = 0.0
        row_started = False

        def flush_row() -> None:
            nonlocal row_width, row_started
            row_width = 0.0
            row_started = False

        try:
            for segment in segments:
                text = segment.get("text", "")
                if not text:
                    continue
                harmony = bool(segment.get("harmony"))
                for piece in self._split_mono_text(text, inner, lyric_size):
                    piece_w = self._lyric_text_width(piece, lyric_size)
                    if row_started and row_width + piece_w > inner:
                        cur_y += lyric_h
                        flush_row()
                    draw_x = x + margin + row_width
                    self.set_font(MONO, size=lyric_size)
                    if harmony:
                        self.set_text_color(*self.theme.harmony)
                    else:
                        self.set_text_color(*self.theme.text)
                    self.set_xy(draw_x, cur_y)
                    self.cell(
                        piece_w,
                        lyric_h,
                        _pdf_text(piece),
                        new_x=XPos.RIGHT,
                        new_y=YPos.TOP,
                    )
                    if harmony:
                        underline_y = cur_y + lyric_h - 0.55
                        self.set_draw_color(*self.theme.harmony)
                        self.set_line_width(0.1)
                        self.line(draw_x, underline_y, draw_x + piece_w, underline_y)
                    row_width += piece_w
                    row_started = True
        finally:
            self.c_margin = margin
        self.set_xy(x, cur_y + lyric_h)
        return cur_y + lyric_h - y

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
        self._advance_in_column(x, 0.5)

    def _lyric_text_width(self, text: str, size: float) -> float:
        self.set_font(MONO, size=size)
        return self.get_string_width(_pdf_text(text))

    def _lyric_inner_max_width(self, column_width: float) -> float:
        return max(10.0, column_width - 2 * self.c_margin)

    def _advance_in_column(self, column_x: float, dy: float) -> None:
        self.set_xy(column_x, self.get_y() + dy)

    def _ensure_vertical_space(
        self,
        height: float,
        song_first_page: int,
        *,
        column_x: float | None = None,
        column_w: float | None = None,
    ) -> tuple[float, float]:
        if (
            not self._single_song_page
            and self.get_y() + height > self.song_body_bottom()
        ):
            self.add_page()
        if column_x is not None and column_w is not None:
            return column_x, column_w
        return self.lyric_column(song_first_page)

    def _fit_mono_line_font_size(
        self, lines: list[str], column_width: float, base_size: float
    ) -> float:
        inner_max = self._lyric_inner_max_width(column_width)
        size = base_size
        while size > MIN_LYRIC_FONT_PT:
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
        song_first_page: int,
    ) -> float:
        """Match HTML: monospace chord row (_build_chord_line) then lyric, same font."""
        lyric = _lyric_plain(block)
        chords = block.get("chords") or []
        segments = _lyric_segments(block)
        column_x, column_w = x, width
        key = song_key or "C"
        chord_line = ""
        if chords:
            chord_line = _build_chord_line(lyric, chords, key).rstrip()
            lyric_size = self._fit_mono_line_font_size(
                [lyric, chord_line], width, layout.lyric
            )
            chord_line = _build_chord_line(lyric, chords, key).rstrip()
        else:
            lyric_size = self._fit_mono_line_font_size([lyric], width, layout.lyric)

        lyric_h = _line_height_mm(lyric_size)
        lyric_rows = self._count_wrapped_segment_rows(segments, width, lyric_size)
        lyric_block_h = lyric_rows * lyric_h
        chord_h = _line_height_mm(lyric_size) if chords else 0.0
        pair_h = lyric_block_h + (chord_h + 0.35 if chords else 0.0) + 0.2
        x, width = self._ensure_vertical_space(
            pair_h,
            song_first_page,
            column_x=column_x,
            column_w=column_w,
        )
        y0 = self.get_y()

        self.set_auto_page_break(False)
        try:
            y_cursor = y0
            if chords:
                self.set_xy(x, y_cursor)
                self.set_font(MONO, size=lyric_size)
                self.set_text_color(*self.theme.accent)
                for chord_row in self._split_mono_text(
                    chord_line, self._lyric_inner_max_width(width), lyric_size
                ):
                    row_w = self._lyric_text_width(chord_row, lyric_size)
                    self.set_xy(x, y_cursor)
                    self.cell(
                        row_w,
                        chord_h,
                        _pdf_text(chord_row),
                        align=Align.L,
                        new_x=XPos.LEFT,
                        new_y=YPos.TOP,
                    )
                    y_cursor += chord_h
                y_cursor += 0.15
            lyric_used = self._render_styled_mono_line(
                x, y_cursor, width, lyric_h, segments, lyric_size
            )
            self.set_xy(x, y_cursor + lyric_used)
        finally:
            if not self._single_song_page:
                self.set_auto_page_break(True, margin=14)
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
        prior_single = self._single_song_page
        prior_break = self.auto_page_break
        prior_margin = self.b_margin
        self._single_song_page = True
        self.set_auto_page_break(False)

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

        main_x, main_w = self.lyric_column(song_first_page)
        for section in song.get("sections") or []:
            if section.get("type") == "comment":
                for block in section.get("blocks") or []:
                    if block.get("kind") == "note":
                        self.draw_info_box(block.get("text", ""), layout, main_w, main_x)
                continue

        chart_sections = self._chart_sections(song)
        if layout.columns >= 2 and len(chart_sections) >= 2:
            gutter = 4.0
            col_w = (main_w - gutter) / 2
            left_x = main_x
            right_x = main_x + col_w + gutter
            left_secs, right_secs = self._partition_sections_two_column(
                chart_sections, layout, song_key, col_w
            )
            y_start = self.get_y()
            y_left = self._render_chart_column(
                left_secs,
                layout,
                song_key,
                left_x,
                col_w,
                y_start,
                song_first_page,
            )
            y_right = self._render_chart_column(
                right_secs,
                layout,
                song_key,
                right_x,
                col_w,
                y_start,
                song_first_page,
            )
            self.set_y(max(y_left, y_right))
        else:
            y_start = self.get_y()
            self.set_xy(main_x, y_start)
            started = False
            for section in chart_sections:
                started = self._render_chart_section(
                    section,
                    layout,
                    song_key,
                    main_x,
                    main_w,
                    song_first_page,
                    chart_section_started=started,
                )

        self._single_song_page = prior_single
        self.set_auto_page_break(prior_break, margin=prior_margin)

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
    pdf._page_nav_by_page = build_page_nav(songs, song_start_pages)
    pdf.add_page()
    pdf.render_setlist(gig_data, songs, song_start_pages)

    for song in songs:
        pdf.add_page()
        pdf.set_auto_page_break(auto=True, margin=14)
        layout = layouts[song["slug"]]
        pdf.render_song(song, layout=layout)

    return bytes(pdf.output())
