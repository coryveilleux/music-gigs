from __future__ import annotations

import csv
import io
from typing import TYPE_CHECKING

from music_gigs.loader import format_duration
from music_gigs.models import DEFAULT_TEXT_TEMPLATE, SetList

if TYPE_CHECKING:
    from music_gigs.models import Band, Song


def catalog_songs_sorted(band: Band, *, active_only: bool = True) -> list[Song]:
    songs = [s for s in band.catalog.songs if s.active or not active_only]
    return sorted(
        songs,
        key=lambda s: (
            band.member_name(s.lead_singer).lower(),
            s.title.lower(),
        ),
    )


def render_catalog_review(band: Band, *, active_only: bool = True) -> str:
    """Aligned catalog list: singer - key - title: artist (one per line)."""
    songs = catalog_songs_sorted(band, active_only=active_only)
    if not songs:
        return ""

    rows = [
        (
            band.member_name(song.lead_singer),
            song.key,
            song.title,
            song.original_artist,
        )
        for song in songs
    ]
    max_singer = max(len(singer) for singer, _, _, _ in rows)
    max_key = max(len(key) for _, key, _, _ in rows)

    lines = [
        f"{singer:<{max_singer}} - {key:<{max_key}} - {title}: {artist}"
        for singer, key, title, artist in rows
    ]
    return "\n".join(lines) + "\n"


def _song_field_values(band: Band, entry) -> dict[str, str]:
    song = entry.song
    return {
        "set_number": str(entry.set_number),
        "lead_singer": band.member_name(song.lead_singer),
        "key": song.key,
        "title": song.title,
        "original_artist": song.original_artist,
        "duration": format_duration(song.duration_seconds),
        "notes": (song.notes or "").replace("\n", " ").strip(),
    }


def render_text(
    band: Band,
    setlist: SetList,
    columns: list[str] | None = None,
    template: str = DEFAULT_TEXT_TEMPLATE,
) -> str:
    lines: list[str] = []
    sets = setlist.sets

    for set_number in sorted(sets):
        lines.append(f"Set {set_number}")
        lines.append("-" * 6)
        for entry in sets[set_number]:
            values = _song_field_values(band, entry)
            if columns:
                line = " - ".join(values[col] for col in columns if col in values and col != "set_number")
            else:
                line = template.format(**values)
            lines.append(line)
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def render_csv(
    band: Band,
    setlist: SetList,
    columns: list[str],
) -> str:
    output = io.StringIO()
    labels = {
        "set_number": "Set",
        "lead_singer": "Lead Singer",
        "key": "Key",
        "title": "Title",
        "original_artist": "Original Artist",
        "duration": "Duration",
        "notes": "Notes",
    }
    writer = csv.writer(output)
    writer.writerow([labels.get(col, col) for col in columns])

    for entry in setlist.songs:
        values = _song_field_values(band, entry)
        writer.writerow([values.get(col, "") for col in columns])

    return output.getvalue()
