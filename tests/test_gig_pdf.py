from pathlib import Path

from music_gigs.gig_html import build_gig_data
from music_gigs.gig_pdf import render_gig_pdf


def test_pdf_chord_line_aligns_with_lyrics_like_html():
    from music_gigs.chordpro import _build_chord_line
    from music_gigs.gig_html import build_gig_data

    root = Path(__file__).resolve().parents[1]
    band_dir = root / "BailMoneyBand"
    set_path = band_dir / "sets" / "stone-cow-2026-09-19.yaml"
    gig_data = build_gig_data(band_dir, set_path)
    song = next(s for s in gig_data["songs"] if s["slug"] == "buy-me-a-boat")
    chorus = next(s for s in song["sections"] if s["type"] == "chorus" and s.get("number") == 1)
    block = next(b for b in chorus["blocks"] if b["kind"] == "lyric")
    lyric = block["lyrics"]
    chord_line = _build_chord_line(lyric, block["chords"], "D")
    d_pos = next(c["pos"] for c in block["chords"] if c["chord"] == "D")
    assert lyric[d_pos : d_pos + 4] == "boat"
    assert chord_line[d_pos] == "D"


def test_chord_lyric_line_does_not_wrap_in_pdf():
    from music_gigs.gig_html import build_gig_data
    from music_gigs.gig_pdf import GigBookPDF, SongLayout

    root = Path(__file__).resolve().parents[1]
    band_dir = root / "BailMoneyBand"
    set_path = band_dir / "sets" / "stone-cow-2026-09-19.yaml"
    gig_data = build_gig_data(band_dir, set_path)
    song = next(s for s in gig_data["songs"] if s["slug"] == "buy-me-a-boat")
    chorus = next(s for s in song["sections"] if s["type"] == "chorus" and s.get("number") == 1)
    block = next(b for b in chorus["blocks"] if b["kind"] == "lyric")

    pdf = GigBookPDF()
    pdf.add_page()
    layout = SongLayout.from_scale(1.0)
    main_x, main_w, _, _ = pdf.column_geometry()
    y0 = pdf.get_y()
    pdf.render_tight_lyric(block, main_x, main_w, layout, song.get("key") or "D")
    # One chord row + one lyric row (not wrapped mid-line).
    assert pdf.get_y() - y0 < 20


def test_buy_me_a_boat_chart_page_count():
    root = Path(__file__).resolve().parents[1]
    band_dir = root / "BailMoneyBand"
    set_path = band_dir / "sets" / "stone-cow-2026-09-19.yaml"
    gig_data = build_gig_data(band_dir, set_path)
    song = next(s for s in gig_data["songs"] if s["slug"] == "buy-me-a-boat")
    from music_gigs.gig_pdf import GigBookPDF

    pdf = GigBookPDF()
    pdf.add_page()
    pdf.render_song(song)
    assert len(pdf.pages) <= 2


def test_render_stone_cow_pdf_prototype():
    root = Path(__file__).resolve().parents[1]
    band_dir = root / "BailMoneyBand"
    set_path = band_dir / "sets" / "stone-cow-2026-09-19.yaml"
    gig_data = build_gig_data(band_dir, set_path)
    pdf_bytes = render_gig_pdf(gig_data, song_limit=3)
    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) > 5000
    page_count = pdf_bytes.count(b"/Type /Page")
    assert page_count >= 4


def test_render_full_pdf_smoke():
    root = Path(__file__).resolve().parents[1]
    band_dir = root / "BailMoneyBand"
    set_path = band_dir / "sets" / "pilot-gig.yaml"
    if not set_path.exists():
        return
    gig_data = build_gig_data(band_dir, set_path)
    pdf_bytes = render_gig_pdf(gig_data)
    assert pdf_bytes.startswith(b"%PDF")
