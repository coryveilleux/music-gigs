#!/usr/bin/env -S uv run --script
"""Refresh Bail Money Band songs.yaml from songs.txt + Apple Music playlist."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from music_gigs.apple_music import (
    PlaylistTrack,
    fetch_apple_music_web_playlist,
    lookup_itunes_track,
    normalize_track_title,
    parse_apple_music_tsv,
)
from music_gigs.slug import slugify

PLAYLIST_URL = (
    "https://music.apple.com/us/playlist/country-tunes-pete-towler/pl.u-X8GRtD9yWeJ"
)

# songs.txt title aliases -> normalized playlist title
TITLE_ALIASES: dict[str, str] = {
    "wildknight": "wildnight",
    "gimme3steps": "gimmethreesteps",
    "folsom": "folsomprisonblues",
    "layyoudown": "idlovetolayyoudown",
    "nationwide": "imbadimnationwide",
    "maryjane": "maryjaneslastdance",
    "whatkindofman": "whatkindaman",
    "muchtooyoungtofeelthisold": "muchtooyoungtofeelthisdamnold",
    "morethanmyhometown": "morethanmyhometown",
    "halfofme": "halfofme",
    "heygoodlookin": "heygoodlookin",
    "fishininthedark": "fishininthedark",
    "downtothehonkytonk": "downtothehonkytonk",
    "longlivecowgirls34scow": "longlivecowgirls",
    "anythingbutmine": "anythingbutmine",
    "iwontbackdown": "iwontbackdown",
    "pourmeadrink": "pourmeadrink",
    "countryroads": "takemehomecountryroads",
    "shouldabeenacowboy": "shouldvebeenacowboy",
    "openthegate": "openthegate",
    "stayhereanddrink": "ithinkilljuststayhereanddrink",
    "beerwithmyfriends": "friendsinlowplaces",
    "workingmanblues": "workinmanblues",
    "canttoyousee": "canttoyousee",
    "countryassshit": "countryashit",
    "honkytonkman": "honkytonkman",
    "sweethomealabama": "sweethomealabama",
    "ontheroadagain": "ontheroadagain",
    "birthdaytoyou": "birthday",
    "birthday": "birthday",
    "lookingforlove": "lookinforlove",
    "drinkinmyhard": "drinkinmyhand",
}

CHART_NOTES: dict[str, dict[str, list[str] | str]] = {
    "20-cigarettes": {
        "structure": "V1 C1 V2 C2 Inst(V) B V3 Inst(V)",
        "intro": [
            "Vocal and guitar only",
            '"We burned..." enters on B section feel, then D on "13 cigarettes"',
        ],
        "outro": [
            "Instrumental",
            "End on last chord of progression",
        ],
    },
    "when-it-rains-it-pours": {
        "structure": "V1 C1 V2 C2 V3 C3 B",
        "intro": [
            "Vocal pickup",
            "All but B until 2nd half of verse",
        ],
    },
}


def _norm_alias(title: str) -> str:
    return normalize_track_title(title)


def _parse_songs_txt(path: Path) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        key, title = line.split(" ", maxsplit=1)
        entries.append({"key": key, "title": title.strip()})
    return entries


def _match_playlist_track(
    catalog_title: str, playlist_index: dict[str, tuple[str, str]]
) -> tuple[str, str] | None:
    norm = _norm_alias(catalog_title)
    norm = TITLE_ALIASES.get(norm, norm)
    if norm in playlist_index:
        return playlist_index[norm]
    for playlist_norm, value in playlist_index.items():
        if norm in playlist_norm or playlist_norm in norm:
            return value
    return None


def _build_playlist_index(
    playlist_tracks: list,
) -> dict[str, tuple[str, str]]:
    index: dict[str, tuple[str, str]] = {}
    for track in playlist_tracks:
        index[_norm_alias(track.title)] = (track.title, track.artist)
    return index


def _enrich_duration(title: str, artist: str) -> int:
    try:
        result = lookup_itunes_track(title, artist)
    except Exception:
        return 0
    if not result:
        return 0
    return result.duration_seconds

def _write_chopro_stub(
    charts_dir: Path,
    title: str,
    artist: str,
    key: str,
    slug: str,
    extra_comments: list[str] | None = None,
) -> None:
    path = charts_dir / f"{slug}.chopro"
    if path.exists():
        return
    comments = ["Chart pending — add chords and lyrics from rehearsal."]
    if extra_comments:
        comments.extend(extra_comments)
    comment_block = "\n".join(f"{{comment: {line}}}" for line in comments)
    body = f"""{{title: {title}}}
{{artist: {artist}}}
{{key: {key}}}
{comment_block}

{{start_of_verse}}
[TBD]
{{end_of_verse}}
"""
    path.write_text(body, encoding="utf-8")


def _merge_chart_notes(charts_dir: Path, slug: str, notes: dict) -> None:
    path = charts_dir / f"{slug}.chopro"
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    additions: list[str] = []
    structure = notes.get("structure")
    if structure and f"{{comment: Structure:" not in text:
        additions.append(f"{{comment: Structure: {structure}}}")
    for label, key in (("intro", "intro"), ("outro", "outro")):
        items = [item for item in notes.get(key, []) if item]
        if not items:
            continue
        block_name = f"start_of_{key}"
        if block_name in text:
            continue
        lines = "\n".join(items)
        additions.append(f"{{start_of_{key}}}\n{lines}\n{{end_of_{key}}}")
    if not additions:
        return
    marker = "\n{start_of_intro"
    if marker in text:
        text = text.replace(marker, "\n" + "\n".join(additions) + marker, 1)
    else:
        header_end = text.find("\n\n")
        if header_end == -1:
            text = text.rstrip() + "\n\n" + "\n".join(additions) + "\n"
        else:
            text = (
                text[:header_end]
                + "\n"
                + "\n".join(additions)
                + text[header_end:]
            )
    path.write_text(text, encoding="utf-8")


def _match_tsv_track(
    catalog_title: str, tracks: list[PlaylistTrack]
) -> PlaylistTrack | None:
    norm = TITLE_ALIASES.get(_norm_alias(catalog_title), _norm_alias(catalog_title))
    index = {_norm_alias(track.title): track for track in tracks}
    if norm in index:
        return index[norm]
    for playlist_norm, track in index.items():
        if norm in playlist_norm or playlist_norm in norm:
            return track
    return None


def merge_playlist_tsv(band_dir: Path, tsv_path: Path) -> None:
    """Merge writers, artist, and duration from an Apple Music playlist TSV export."""
    songs_yaml = band_dir / "songs.yaml"
    with songs_yaml.open(encoding="utf-8") as f:
        raw = f.read()
    header = ""
    if raw.startswith("#"):
        header, raw = raw.split("\n", 1)
        header = header + "\n"
        if raw.startswith("#"):
            header, raw = raw.split("\n", 1)
            header = header + "\n"
        if raw.startswith("#"):
            header, raw = raw.split("\n", 1)
            header = header + "\n"
        raw = raw.lstrip("\n")

    catalog = yaml.safe_load(raw) or {"songs": []}
    tracks = parse_apple_music_tsv(tsv_path)

    matched = 0
    unmatched: list[str] = []
    for song in catalog["songs"]:
        track = _match_tsv_track(song["title"], tracks)
        if not track:
            unmatched.append(song["title"])
            continue
        matched += 1
        song["original_artist"] = track.artist
        song["duration_seconds"] = track.duration_seconds
        song["writers"] = track.writers

    header = (
        "# Bail Money Band song catalog\n"
        "# Keys are performance keys. Chart/arrangement details live in charts/*.chopro\n"
        "# Metadata enriched from Apple Music playlist export\n\n"
    )
    with songs_yaml.open("w", encoding="utf-8") as f:
        f.write(header)
        yaml.dump(
            {"songs": catalog["songs"]},
            f,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )

    print(f"Merged playlist data for {matched} songs into {songs_yaml}")
    if unmatched:
        print(f"No playlist match for {len(unmatched)} catalog songs:")
        for title in unmatched:
            print(f"  - {title}")


def update_catalog(
    band_dir: Path,
    playlist_url: str,
    skip_itunes: bool = False,
) -> None:
    songs_txt = band_dir / "songs.txt"
    songs_yaml = band_dir / "songs.yaml"
    charts_dir = band_dir / "charts"
    charts_dir.mkdir(exist_ok=True)

    playlist_tracks = fetch_apple_music_web_playlist(playlist_url)
    # Stop before featured-artist section misparses
    playlist_tracks = playlist_tracks[:48]
    playlist_index = _build_playlist_index(playlist_tracks)
    matched_playlist_norms: set[str] = set()
    duration_cache: dict[tuple[str, str], int] = {}

    def cached_duration(title: str, artist: str) -> int:
        if skip_itunes:
            return 0
        cache_key = (title.lower(), artist.lower())
        if cache_key not in duration_cache:
            duration_cache[cache_key] = _enrich_duration(title, artist)
            time.sleep(0.4)
        return duration_cache[cache_key]

    catalog_entries = _parse_songs_txt(songs_txt)
    songs_out: list[dict] = []

    for entry in catalog_entries:
        catalog_title = entry["title"]
        key = entry["key"]
        if key.isdigit():
            key_comment = f"Capo {key}"
            key = "G"
        else:
            key_comment = ""

        match = _match_playlist_track(catalog_title, playlist_index)
        if match:
            playlist_title, artist = match
            matched_playlist_norms.add(_norm_alias(playlist_title))
            lookup_title = playlist_title
        else:
            playlist_title = ""
            artist = ""
            lookup_title = catalog_title
            if not skip_itunes:
                try:
                    itunes = lookup_itunes_track(catalog_title)
                except Exception:
                    itunes = None
                if itunes:
                    lookup_title = itunes.title
                    artist = itunes.artist

        duration = cached_duration(lookup_title, artist)

        song_obj = {
            "title": catalog_title,
            "original_artist": artist or "",
            "key": key,
            "duration_seconds": duration,
            "active": True,
            "writers": [],
        }
        songs_out.append(song_obj)

        slug = slugify(catalog_title)
        extra_comments = [key_comment] if key_comment else []
        _write_chopro_stub(
            charts_dir, catalog_title, artist, key, slug, extra_comments
        )
        if slug in CHART_NOTES:
            _merge_chart_notes(charts_dir, slug, CHART_NOTES[slug])

    # Playlist songs not already matched from songs.txt
    for track in playlist_tracks:
        norm = _norm_alias(track.title)
        if norm in matched_playlist_norms:
            continue
        duration = cached_duration(track.title, track.artist)
        songs_out.append(
            {
                "title": track.title,
                "original_artist": track.artist,
                "key": "",
                "duration_seconds": duration,
                "active": True,
                "writers": [],
            }
        )
        slug = slugify(track.title)
        _write_chopro_stub(charts_dir, track.title, track.artist, "", slug)

    header = (
        "# Bail Money Band song catalog\n"
        "# Keys are performance keys. Chart/arrangement details live in charts/*.chopro\n"
        "# Metadata enriched from Apple Music playlist + iTunes lookup\n\n"
    )
    with songs_yaml.open("w", encoding="utf-8") as f:
        f.write(header)
        yaml.dump(
            {"songs": songs_out},
            f,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )

    print(f"Wrote {len(songs_out)} songs to {songs_yaml}")
    chart_count = len(list(charts_dir.glob("*.chopro")))
    print(f"Charts directory has {chart_count} .chopro files")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--band-dir",
        type=Path,
        default=Path("BailMoneyBand"),
        help="Band directory (default: BailMoneyBand)",
    )
    parser.add_argument(
        "--playlist-url",
        default=PLAYLIST_URL,
        help="Public Apple Music playlist URL",
    )
    parser.add_argument(
        "--playlist-tsv",
        type=Path,
        help="Merge metadata from Apple Music playlist TSV export (no full rebuild)",
    )
    parser.add_argument(
        "--skip-itunes",
        action="store_true",
        help="Skip iTunes duration lookups",
    )
    args = parser.parse_args()
    if args.playlist_tsv:
        if not args.playlist_tsv.exists():
            print(f"Error: {args.playlist_tsv} not found")
            sys.exit(1)
        merge_playlist_tsv(args.band_dir, args.playlist_tsv)
        return
    update_catalog(args.band_dir, args.playlist_url, skip_itunes=args.skip_itunes)


if __name__ == "__main__":
    main()
