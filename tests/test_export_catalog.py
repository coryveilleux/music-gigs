from music_gigs.export import (
    catalog_pdf_layout,
    catalog_pdf_lines_per_page,
    render_catalog_review,
    render_catalog_review_pdf,
)
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


def test_catalog_pdf_layout():
    assert catalog_pdf_lines_per_page(12) == 12
    assert catalog_pdf_lines_per_page(47) == 12
    assert catalog_pdf_lines_per_page(100) == 10
    assert catalog_pdf_layout(47) == (12, 16)


def test_pdf_uses_first_names_and_short_keys():
    band = discover_bands(__import__("pathlib").Path(__file__).resolve().parents[1])[0]
    from music_gigs.export import _align_catalog_rows, _catalog_review_rows

    rows = _catalog_review_rows(band, first_name_only=True, pdf_keys=True)
    singers = {singer for singer, _, _, _ in rows}
    assert "Billy" in singers
    assert "Billy Anderson" not in singers
    keys = {key for _, key, _, _ in rows}
    assert "D mixo" in keys
    assert not any("mixolydian" in key for key in keys)

    lines = _align_catalog_rows(rows)
    assert lines


def test_render_catalog_review_pdf():
    band = discover_bands(__import__("pathlib").Path(__file__).resolve().parents[1])[0]
    pdf_bytes = render_catalog_review_pdf(band)
    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) > 2000
