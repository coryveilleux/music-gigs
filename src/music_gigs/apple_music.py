from __future__ import annotations

import csv
import re
import xml.etree.ElementTree as ET
from codecs import BOM_UTF16_BE, BOM_UTF16_LE, BOM_UTF8
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class PlaylistTrack:
    title: str
    artist: str
    duration_seconds: int
    album: str | None = None
    writers: list[str] = field(default_factory=list)


def _parse_duration_ms(value: str | None) -> int:
    if not value:
        return 0
    try:
        return int(int(value) / 1000)
    except ValueError:
        return 0


def _parse_writers(value: str | None) -> list[str]:
    if not value:
        return []
    cleaned = value.strip()
    if cleaned.lower() in {"not documented", "see-subsong"}:
        return []
    parts = re.split(r"\s*(?:,|&|/)\s*", cleaned)
    return [part.strip() for part in parts if part.strip()]


def _parse_duration_seconds(value: str | None) -> int:
    if not value:
        return 0
    try:
        return int(value)
    except ValueError:
        return 0


def _playlist_text_encoding(path: Path) -> str:
    start = path.read_bytes()[:4]
    if start.startswith(BOM_UTF16_LE) or start.startswith(BOM_UTF16_BE):
        return "utf-16"
    if start.startswith(BOM_UTF8):
        return "utf-8-sig"
    return "utf-8-sig"


def parse_apple_music_tsv(tsv_path: Path) -> list[PlaylistTrack]:
    """Parse an Apple Music playlist tab-separated text export."""
    encoding = _playlist_text_encoding(tsv_path)
    with tsv_path.open(encoding=encoding, newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        if not reader.fieldnames or "Name" not in reader.fieldnames:
            raise ValueError(
                "Not a recognized Apple Music playlist export (expected tab-separated with Name column)"
            )

        tracks: list[PlaylistTrack] = []
        for row in reader:
            title = (row.get("Name") or "").strip()
            if not title:
                continue
            tracks.append(
                PlaylistTrack(
                    title=title,
                    artist=(row.get("Artist") or "Unknown").strip(),
                    duration_seconds=_parse_duration_seconds(row.get("Time")),
                    album=(row.get("Album") or "").strip() or None,
                    writers=_parse_writers(row.get("Composer")),
                )
            )
        return tracks


def parse_playlist(path: Path) -> list[PlaylistTrack]:
    """Parse an Apple Music playlist export (TSV or Library XML)."""
    if path.suffix.lower() == ".xml":
        return parse_apple_music_playlist(path)

    with path.open("rb") as f:
        start = f.read(256).lstrip()

    if start.startswith(b"<?xml") or start.startswith(b"<plist"):
        return parse_apple_music_playlist(path)

    return parse_apple_music_tsv(path)


def parse_apple_music_playlist(xml_path: Path) -> list[PlaylistTrack]:
    """Parse an Apple Music / iTunes Library XML export for playlist tracks."""
    tree = ET.parse(xml_path)
    root = tree.getroot()

    tracks_by_id: dict[str, dict[str, str]] = {}
    for dict_elem in root.iter("dict"):
        children = list(dict_elem)
        if not children:
            continue
        i = 0
        while i < len(children):
            child = children[i]
            if child.tag == "key" and child.text == "Tracks":
                tracks_dict = children[i + 1]
                for track_dict in tracks_dict:
                    if track_dict.tag != "dict":
                        continue
                    track_data: dict[str, str] = {}
                    j = 0
                    track_children = list(track_dict)
                    while j < len(track_children):
                        key_elem = track_children[j]
                        if key_elem.tag == "key":
                            val_elem = track_children[j + 1]
                            if val_elem.text is not None:
                                track_data[key_elem.text] = val_elem.text
                            j += 2
                        else:
                            j += 1
                    track_id = track_data.get("Track ID")
                    if track_id:
                        tracks_by_id[track_id] = track_data
                break
            i += 1

    playlist_tracks: list[PlaylistTrack] = []
    for dict_elem in root.iter("dict"):
        children = list(dict_elem)
        i = 0
        while i < len(children):
            child = children[i]
            if child.tag == "key" and child.text == "Playlist Items":
                items_array = children[i + 1]
                for item_dict in items_array:
                    if item_dict.tag != "dict":
                        continue
                    item_children = list(item_dict)
                    j = 0
                    track_id = None
                    while j < len(item_children):
                        key_elem = item_children[j]
                        if key_elem.tag == "key" and key_elem.text == "Track ID":
                            track_id = item_children[j + 1].text
                            break
                        j += 2
                    if track_id and track_id in tracks_by_id:
                        data = tracks_by_id[track_id]
                        playlist_tracks.append(
                            PlaylistTrack(
                                title=data.get("Name", "Unknown"),
                                artist=data.get("Artist", "Unknown"),
                                duration_seconds=_parse_duration_ms(
                                    data.get("Total Time")
                                ),
                                album=data.get("Album"),
                                writers=_parse_writers(data.get("Composer")),
                            )
                        )
                return playlist_tracks
            i += 1

    return playlist_tracks
