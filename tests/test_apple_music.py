from pathlib import Path

import pytest

from music_gigs.apple_music import (
    _parse_writers,
    parse_apple_music_tsv,
    parse_playlist,
)

TSV_SAMPLE = """\
Name\tArtist\tComposer\tAlbum\tTime
Big River\tGrateful Dead\tJohnny Cash\tDownload Series Vol. 8\t294
Dead Flowers\tThe Rolling Stones\tMick Jagger & Keith Richards\tSticky Fingers\t245
"""

XML_SAMPLE = """\
<?xml version="1.0" encoding="UTF-8"?>
<plist version="1.0">
<dict>
  <key>Tracks</key>
  <dict>
    <key>1</key>
    <dict>
      <key>Track ID</key><integer>1</integer>
      <key>Name</key><string>Test Song</string>
      <key>Artist</key><string>Test Artist</string>
      <key>Album</key><string>Test Album</string>
      <key>Total Time</key><integer>213000</integer>
      <key>Composer</key><string>Writer One &amp; Writer Two</string>
    </dict>
  </dict>
  <key>Playlists</key>
  <array>
    <dict>
      <key>Playlist Items</key>
      <array>
        <dict>
          <key>Track ID</key><integer>1</integer>
        </dict>
      </array>
    </dict>
  </array>
</dict>
</plist>
"""


def test_parse_writers():
    assert _parse_writers("Mick Jagger & Keith Richards") == [
        "Mick Jagger",
        "Keith Richards",
    ]
    assert _parse_writers("Not Documented") == []
    assert _parse_writers(None) == []


def test_parse_apple_music_tsv(tmp_path: Path):
    path = tmp_path / "playlist.txt"
    path.write_text(TSV_SAMPLE, encoding="utf-8")
    tracks = parse_apple_music_tsv(path)
    assert len(tracks) == 2
    assert tracks[0].title == "Big River"
    assert tracks[0].artist == "Grateful Dead"
    assert tracks[0].duration_seconds == 294
    assert tracks[0].writers == ["Johnny Cash"]
    assert tracks[1].writers == ["Mick Jagger", "Keith Richards"]


def test_parse_playlist_auto_detects_tsv(tmp_path: Path):
    path = tmp_path / "playlist.txt"
    path.write_text(TSV_SAMPLE, encoding="utf-8")
    tracks = parse_playlist(path)
    assert len(tracks) == 2


def test_parse_playlist_auto_detects_xml(tmp_path: Path):
    path = tmp_path / "playlist.xml"
    path.write_text(XML_SAMPLE, encoding="utf-8")
    tracks = parse_playlist(path)
    assert len(tracks) == 1
    assert tracks[0].title == "Test Song"
    assert tracks[0].writers == ["Writer One", "Writer Two"]


def test_parse_apple_music_tsv_invalid(tmp_path: Path):
    path = tmp_path / "bad.txt"
    path.write_text("foo,bar\n1,2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Name column"):
        parse_apple_music_tsv(path)


def test_parse_user_playlist():
    user_file = Path.home() / "Documents" / "The Otters.txt"
    if not user_file.exists():
        pytest.skip("User playlist file not available")
    tracks = parse_playlist(user_file)
    assert len(tracks) > 100
    assert tracks[0].title == "Big River"
    assert tracks[0].duration_seconds == 294
