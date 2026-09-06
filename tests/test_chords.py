from music_gigs.chords import chord_to_nashville, transpose_chord


def test_transpose_chord():
    assert transpose_chord("D", 2) == "E"
    assert transpose_chord("Am", -2) == "Gm"
    assert transpose_chord("A/C#", 0) == "A/C#"
    assert transpose_chord("F#m", 1) == "Gm"


def test_nashville_in_key_a():
    assert chord_to_nashville("A", "A") == "1"
    assert chord_to_nashville("F#m", "A") == "6m"
    assert chord_to_nashville("D", "A") == "4"
    assert chord_to_nashville("E", "A") == "5"


def test_nashville_in_key_d():
    assert chord_to_nashville("Bm", "D") == "6m"
    assert chord_to_nashville("G", "D") == "4"


def test_nashville_on_separate_line():
    from music_gigs.chordpro import (
        _build_chord_line,
        _build_nashville_line,
        _chord_positions,
    )

    line = "I heard you're [A/C#]doing [Bm]fine, got pro-[G]moted"
    lyrics, chords = _chord_positions(line)
    chord_line = _build_chord_line(lyrics, chords, "D")
    nashville_line = _build_nashville_line(lyrics, chords, "D")

    bm_pos = len("I heard you're doing ")
    ac_pos = len("I heard you're ")

    assert chord_line[bm_pos : bm_pos + 2] == "Bm"
    assert "(Bm" not in chord_line
    assert nashville_line[bm_pos : bm_pos + 2] == "6m"
    assert chord_line[ac_pos : ac_pos + 4] == "A/C#"
    # "5" centered under four-character "A/C#"
    assert nashville_line[ac_pos + 1] == "5"
