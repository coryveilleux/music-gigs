from music_gigs.export import render_catalog_review
from music_gigs.loader import discover_bands


def test_render_catalog_review_sorted_and_aligned():
    band = discover_bands(__import__("pathlib").Path(__file__).resolve().parents[1])[0]
    text = render_catalog_review(band)
    lines = [line for line in text.strip().splitlines() if line]
    assert lines

    singers = [line.split(" - ", 1)[0] for line in lines]
    assert singers == sorted(singers, key=str.lower)

    dash_positions = [line.index(" - ") for line in lines]
    assert len(set(dash_positions)) == 1

    title_starts = []
    for line in lines:
        _, rest = line.split(" - ", 1)
        _, rest = rest.split(" - ", 1)
        title_starts.append(line.index(rest))
    assert len(set(title_starts)) == 1

    assert ": " in lines[0]
    assert " - " in lines[0]
