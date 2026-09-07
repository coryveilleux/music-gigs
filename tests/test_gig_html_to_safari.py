from music_gigs.gig_html import html_to_data_uri


def test_html_to_data_uri():
    uri = html_to_data_uri(b"<html><body>hi</body></html>")
    assert uri.startswith("data:text/html;charset=utf-8;base64,")
    assert "PGh0bWw" in uri
