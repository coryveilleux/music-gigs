from pathlib import Path

from music_gigs.chordpro import (
    chordpro_to_structured,
    parse_chordpro,
    render_chordpro_html,
    section_outline_from_structured,
)
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

    html = _render_lyric_line("And you [Em]met someone", song_key="D")
    assert "And you met someone" in html
    assert "Em" in html
    assert "Emmet" not in html
    assert html.index("Em") < html.index("And you met")


def test_section_outline_hints():
    text = """{title: Test}
{key: D}
{start_of_verse}
Well it's been some [Bm]time you still look like an [D]angel
I heard you're [A]doing fine got promoted back in [D]April
And you [Em]met someone your dad says he's [G]OK
Well I've [Em]never been better things are goin' my [G]way
{end_of_verse}
{start_of_chorus}
I sleep like a [A]baby I never show up [G]late for work
I don't drink whiskey I don't know how it feels to hurt
{end_of_chorus}
"""
    song = parse_chordpro(text)
    structured = chordpro_to_structured(song)
    outline = section_outline_from_structured(structured)
    assert len(outline) == 2
    assert outline[0]["type"] == "verse"
    assert "Bm" in outline[0]["chords"]
    assert outline[0]["start"].startswith("Well it's been")
    assert "goin' my way" in outline[0]["end"]
    assert outline[1]["type"] == "chorus"
    assert "feels to hurt" in outline[1]["end"]


def test_build_pilot_gig():
    root = Path(__file__).resolve().parents[1]
    band_dir = root / "BailMoneyBand"
    set_path = band_dir / "sets" / "pilot-gig.yaml"
    data = build_gig_data(band_dir, set_path)
    assert len(data["sets"]) == 2
    assert len(data["songs"]) == 2
    assert data["songs"][0]["slug"] == "i-never-lie"
    assert data["songs"][0]["sections"]
    assert data["songs"][0]["outline"]
    assert data["songs"][0]["tempo"] == 108
    assert data["songs"][0]["duration_seconds"] == 224
    html = render_gig_html(data)
    assert "I Never Lie" in html
    assert "20 Cigarettes" in html
    assert "transpose-bar" in html
    assert "performance-bar" in html
    assert "view-outline" in html
    assert 'href="#song-i-never-lie"' in html
    assert 'id="song-i-never-lie"' in html
    assert "body_html" not in html
