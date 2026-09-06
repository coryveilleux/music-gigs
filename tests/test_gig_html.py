from pathlib import Path

from music_gigs.chordpro import parse_chordpro, render_chordpro_html
from music_gigs.gig_html import build_gig_data, render_gig_html


def test_parse_chordpro_sections():
    text = """{title: Test Song}
{key: D}
{start_of_verse}
Hello [D]world
{end_of_verse}
{start_of_tab: riff}
e|--0--|
{end_of_tab}
"""
    song = parse_chordpro(text)
    assert song.metadata["title"] == "Test Song"
    html = render_chordpro_html(song)
    assert "Hello world" in html
    assert '<div class="chords">' in html
    assert '<div class="lyrics">' in html
    assert "riff" in html.lower()


def test_chords_above_lyrics():
    from music_gigs.chordpro import _render_lyric_line

    html = _render_lyric_line("And you [Em]met someone")
    assert "And you met someone" in html
    assert "Em" in html
    assert "Emmet" not in html
    assert html.index("Em") < html.index("And you met")


def test_build_pilot_gig():
    root = Path(__file__).resolve().parents[1]
    band_dir = root / "BailMoneyBand"
    set_path = band_dir / "sets" / "pilot-gig.yaml"
    data = build_gig_data(band_dir, set_path)
    assert len(data["sets"]) == 2
    assert len(data["songs"]) == 2
    assert data["songs"][0]["slug"] == "i-never-lie"
    html = render_gig_html(data)
    assert "I Never Lie" in html
    assert "20 Cigarettes" in html
    assert "GIG = " in html
