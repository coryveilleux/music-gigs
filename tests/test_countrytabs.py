from music_gigs.countrytabs import lines_to_chordpro, pre_html_to_lines


def test_pre_html_to_lines_extracts_chords():
    pre_html = """
    Intro: <a href='#' class='chordlink'>D</a>
    I ain't <a href='#' class='chordlink'>G</a>rich
    """
    lines = pre_html_to_lines(pre_html)
    assert "Intro: [D]" in lines[0]
    assert "[G]rich" in lines[1]


def test_lines_to_chordpro_splits_sections():
    lines = [
        "Song Title",
        "By Artist",
        "(Verse 1)",
        "I am [G]happy",
        "(Chorus)",
        "Sing it [D]loud",
    ]
    text = lines_to_chordpro(
        lines,
        title="Song Title",
        artist="Artist",
        key="G",
        source_url="http://example.com",
    )
    assert "{start_of_verse}" in text
    assert "{start_of_chorus}" in text
    assert "I am [G]happy" in text
    assert "Sing it [D]loud" in text
