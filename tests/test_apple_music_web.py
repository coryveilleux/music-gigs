from music_gigs.apple_music import parse_apple_music_web_playlist

SAMPLE_HTML = '''
"artistName":"Tom Petty"
"name":"I Won't Back Down"
"name":"I Won't Back Down"
"artistName":"John Mellencamp"
"name":"Wild Night (feat. Meshell Ndegeocello)"
"name":"Wild Night (feat. Meshell Ndegeocello)"
'''


def test_parse_apple_music_web_playlist():
    tracks = parse_apple_music_web_playlist(SAMPLE_HTML)
    assert len(tracks) == 2
    assert tracks[0].title == "I Won't Back Down"
    assert tracks[0].artist == "Tom Petty"
    assert tracks[1].title == "Wild Night (feat. Meshell Ndegeocello)"
    assert tracks[1].artist == "John Mellencamp"
