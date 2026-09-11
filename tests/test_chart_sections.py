from music_gigs.chart_sections import (
    chart_content_matches,
    cleanup_import_lines,
    infer_sections,
    structure_outline,
)
from music_gigs.countrytabs import lines_to_chordpro


def test_cleanup_drops_tab_staff_and_headers():
    lines = [
        "Johnny Cash - Folsom Prison Blues (Key of [E])",
        "By Mike Terrian - mike_terrian at yahoo.com",
        "|-------------2br-0-|",
        "[E]",
        "I hear the train a comin, It's rollin round the bend.",
    ]
    cleaned = cleanup_import_lines(lines, title="Folsom", artist="Johnny Cash")
    assert cleaned == [
        "[E]",
        "I hear the train a comin, It's rollin round the bend.",
    ]


def test_infer_sections_splits_folsom_like_stanzas():
    lines = cleanup_import_lines(
        [
            "I use this little lick in the beggining & end.",
            "[E]",
            "I hear the train a comin, It's rollin round the bend.",
            "I ain't seen the sunshine since, I don't know when.",
            "[A] [E]",
            "I'm stuck in Folsom Prison, And time keeps draggin on.",
            "[B7] [E]",
            "But that train keeps a rollin on down to San Antone.",
            "When I was just a baby, my mamma told me son.",
            "Always be a good boy don't ever play with guns.",
            "But I shot a man in Reno, Just to watch him die.",
            "When I hear that train a rollin, I hang my head and I cry.",
        ],
        title="Folsom Prison Blues",
        artist="Johnny Cash",
    )
    sections = infer_sections(lines)
    types = [section_type for section_type, _ in sections]
    assert types[0] == "intro"
    assert types.count("verse") >= 2
    assert structure_outline(sections).startswith("I")


def test_lines_to_chordpro_adds_structure_comment():
    text = lines_to_chordpro(
        [
            "(Verse 1)",
            "I am [G]happy",
            "(Chorus)",
            "Sing it [D]loud",
            "(Chorus)",
            "Sing it [D]loud",
        ],
        title="Song Title",
        artist="Artist",
        key="G",
        source_url="http://example.com",
    )
    assert "{comment: Structure:" in text
    assert "{start_of_verse}" in text
    assert "{start_of_chorus}" in text


def test_chart_content_matches_title():
    assert chart_content_matches("More Than My Hometown", ["You've long been on the open road"]) is False
    assert chart_content_matches(
        "More Than My Hometown",
        ["Baby, I could stay right here in this hometown forever"],
    )
