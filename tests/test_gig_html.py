from pathlib import Path

from music_gigs.chordpro import (
    _chord_positions,
    chordpro_to_structured,
    compact_chord_rows,
    detect_repeating_progression,
    parse_chordpro,
    parse_progression_spec,
    render_chordpro_html,
    section_display_title,
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


def test_detect_repeating_progression_buy_me_a_boat():
    root = Path(__file__).resolve().parents[1]
    chart = (root / "BailMoneyBand/charts/buy-me-a-boat.chopro").read_text(encoding="utf-8")
    structured = chordpro_to_structured(parse_chordpro(chart))

    def chords_for(section_type: str) -> list[str]:
        section = next(item for item in structured if item["type"] == section_type)
        seq: list[str] = []
        for block in section["blocks"]:
            if block.get("kind") == "lyric":
                seq.extend(entry["chord"] for entry in block.get("chords", []))
        return seq

    chorus_chords = chords_for("chorus")
    detected = detect_repeating_progression(chorus_chords)
    assert detected["pattern"] == ["D", "G", "D", "A"]
    assert detected["repeat"] == 2
    assert detected["tail"] == []

    compact = compact_chord_rows([], chorus_chords)
    assert compact == [{"chords": ["D", "G", "D", "A"], "repeat": 2}]

    verse_chords = chords_for("verse")
    verse_detected = detect_repeating_progression(verse_chords)
    assert verse_detected["pattern"] == ["D", "G", "D", "A"]
    assert verse_detected["repeat"] == 2

    verse_compact = compact_chord_rows([], verse_chords)
    assert verse_compact[0] == {"chords": ["D", "G", "D", "A"], "repeat": 2}


def test_progression_override():
    structured = chordpro_to_structured(
        parse_chordpro(
            """{comment: progression chorus: D G D A x2}
{start_of_chorus}
[C]test [F]line
{end_of_chorus}
"""
        )
    )
    outline = section_outline_from_structured(
        structured,
        {"chorus": "D G D A x2"},
    )
    assert outline[0]["chord_compact"] == [{"chords": ["D", "G", "D", "A"], "repeat": 2}]
    assert parse_progression_spec("D-G-D-A x2")["repeat"] == 2


def test_lyric_line_without_chords_not_italic_note():
    text = """{start_of_bridge}
[D]To float down on the water with a [G]beer
I hear the Powerball Lotto is a-sitting on a hundred mill
Well, that would buy me a brand new [A]rod and reel
{end_of_bridge}
"""
    structured = chordpro_to_structured(parse_chordpro(text))
    bridge = structured[0]
    assert bridge["blocks"][1]["kind"] == "lyric"
    assert "Powerball" in bridge["blocks"][1]["lyrics"]
    html = render_chordpro_html(parse_chordpro(text))
    assert 'class="note">I hear the Powerball' not in html
    assert "lyric-row" in html


def test_compact_chord_rows():
    rows = compact_chord_rows(
        [
            [{"chord": "D", "pos": 0}, {"chord": "G", "pos": 30}],
            [{"chord": "A", "pos": 40}],
        ],
        ["D", "G", "A"],
    )
    assert rows == [{"chords": ["D", "G"], "repeat": 1}, {"chords": ["A"], "repeat": 1}]

    repeated = compact_chord_rows(
        [
            [{"chord": "D", "pos": 0}, {"chord": "G", "pos": 10}],
            [{"chord": "D", "pos": 0}, {"chord": "A", "pos": 10}],
            [{"chord": "D", "pos": 0}, {"chord": "G", "pos": 10}],
            [{"chord": "D", "pos": 0}, {"chord": "A", "pos": 10}],
        ],
        [],
    )
    assert repeated[0]["chords"] == ["D", "G"]
    assert repeated[1]["chords"] == ["D", "A"]
    assert repeated[0]["repeat"] == 1
    assert repeated[1]["repeat"] == 2


def test_section_numbering():
    text = """{title: Test}
{key: D}
{start_of_verse}
Line one [D]here
{end_of_verse}
{start_of_chorus}
Chorus [G]one
{end_of_chorus}
{start_of_verse}
Line two [A]here
{end_of_verse}
{start_of_chorus}
Chorus [G]two
{end_of_chorus}
{start_of_bridge}
Bridge [Bm]part
{end_of_bridge}
"""
    song = parse_chordpro(text)
    structured = chordpro_to_structured(song)
    assert [s["number"] for s in structured if s["type"] == "verse"] == [1, 2]
    assert [s["number"] for s in structured if s["type"] == "chorus"] == [1, 2]
    assert [s["number"] for s in structured if s["type"] == "bridge"] == [None]

    html = render_chordpro_html(song)
    assert "Verse 1" in html
    assert "Verse 2" in html
    assert "Chorus 1" in html
    assert "Chorus 2" in html
    assert "Bridge" in html
    assert "Bridge 1" not in html

    outline = section_outline_from_structured(structured)
    assert outline[0]["number"] == 1
    assert section_display_title("intro", "4 bars", None) == "Intro — 4 bars"
    assert section_display_title("pre-chorus", "", 2) == "Pre-Chorus 2"


def test_single_section_not_numbered():
    text = """{start_of_verse}
Only [D]verse
{end_of_verse}
{start_of_bridge}
Only [G]bridge
{end_of_bridge}
"""
    structured = chordpro_to_structured(parse_chordpro(text))
    assert structured[0]["number"] is None
    assert structured[1]["number"] is None
    html = render_chordpro_html(parse_chordpro(text))
    assert "Verse 1" not in html
    assert ">Verse</h3>" in html or "section-label\">Verse</h3>" in html


def test_inline_cue_brackets():
    _, chords = _chord_positions("well [G] I could [*STOP] buy me a [A]boat")
    assert chords[0] == {"pos": 5, "chord": "G", "cue": ""}
    assert chords[1] == {"pos": 14, "chord": "", "cue": "STOP"}
    assert chords[2] == {"pos": 24, "chord": "A", "cue": ""}

    _, chord_cue = _chord_positions("[G*HOLD] on the downbeat")
    assert chord_cue[0] == {"pos": 0, "chord": "G", "cue": "HOLD"}

    _, songbook = _chord_positions("but it could [STOP] buy me a [A]boat")
    assert songbook[0] == {"pos": 13, "chord": "", "cue": "STOP"}

    _, annotated = _chord_positions("My [Dm7 (play twice)]lyric line")
    assert annotated[0] == {"pos": 3, "chord": "Dm7", "cue": "(play twice)"}

    text = """{start_of_chorus}
Well, maybe [D]so, but it could [*STOP] buy me a [A]boat
{end_of_chorus}
"""
    structured = chordpro_to_structured(parse_chordpro(text))
    outline = section_outline_from_structured(structured)[0]
    assert outline["chords"] == ["D", "A"]
    html = render_chordpro_html(parse_chordpro(text))
    assert "but it could  buy me a boat" in html
    assert "STOP" in html


def test_inline_text_italic_directives():
    text = """{start_of_chorus}
Well, maybe [D]so, but it could {ti: (STOP)} buy me a [A]boat
{text_italic: hold} on the downbeat
{end_of_chorus}
"""
    structured = chordpro_to_structured(parse_chordpro(text))
    chorus = structured[0]
    line1 = chorus["blocks"][0]
    assert line1["lyrics"] == "Well, maybe so, but it could  buy me a boat"
    assert any(segment.get("direction") for segment in line1["segments"])
    assert any(segment["text"] == "(STOP)" for segment in line1["segments"])

    line2 = chorus["blocks"][1]
    assert line2["lyrics"] == "on the downbeat"
    assert line2["segments"][0]["text"] == "hold"
    assert line2["segments"][0]["direction"] is True

    html = render_chordpro_html(parse_chordpro(text))
    assert 'class="inline-direction">(STOP)</span>' in html
    assert 'class="inline-direction">hold</span>' in html
    assert "{ti:" not in html


def test_chord_progression_order_and_inline_notation():
    text = """{start_of_chorus}
Play [C]soft here
{c: go quiet — stop time on beat 3}
[C]loud [F]again [C]now [G]end
|C| |F| |C| |G|
{end_of_chorus}
"""
    structured = chordpro_to_structured(parse_chordpro(text))
    outline = section_outline_from_structured(structured)[0]
    assert outline["chords"] == ["C", "C", "F", "C", "G", "C", "F", "C", "G"]
    assert any(block.get("inline") for block in structured[0]["blocks"] if block["kind"] == "note")

    harmony_text = """{start_of_verse}
Lead line and <<harmony line>> here
{harmony: full backing vocal phrase}
{end_of_verse}
"""
    song = parse_chordpro(harmony_text)
    html = render_chordpro_html(song)
    assert 'class="harmony"' in html
    assert "full backing vocal phrase" in html


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
    assert outline[0]["number"] is None
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
