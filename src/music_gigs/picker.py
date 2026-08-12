from __future__ import annotations

import random
from typing import TYPE_CHECKING

from music_gigs.models import GigConfig, Song

if TYPE_CHECKING:
    from music_gigs.models import Band


def filter_songs(band: Band, config: GigConfig) -> tuple[list[Song], list[str]]:
    """Return eligible songs and any filter warnings."""
    warnings: list[str] = []
    eligible: list[Song] = []

    for song in band.catalog.songs:
        if not song.active:
            continue
        if song.lead_singer in config.absent_members:
            continue
        missing = [
            field
            for field, value in [
                ("title", song.title),
                ("original_artist", song.original_artist),
                ("key", song.key),
                ("lead_singer", song.lead_singer),
                ("duration_seconds", song.duration_seconds),
            ]
            if not value
        ]
        if missing:
            warnings.append(f'"{song.title}" skipped: missing {", ".join(missing)}')
            continue
        eligible.append(song)

    return eligible, warnings


def pick_songs_for_duration(
    songs: list[Song],
    duration_minutes: int,
    tolerance_minutes: int = 5,
    *,
    seed: int | None = None,
) -> list[Song]:
    """Pick a subset of songs closest to target duration without exceeding tolerance."""
    if not songs:
        return []

    target_seconds = duration_minutes * 60
    max_seconds = target_seconds + tolerance_minutes * 60
    rng = random.Random(seed)
    shuffled = songs.copy()
    rng.shuffle(shuffled)

    selected: list[Song] = []
    total = 0
    for song in shuffled:
        if total + song.duration_seconds <= max_seconds:
            selected.append(song)
            total += song.duration_seconds

    if not selected and shuffled:
        shortest = min(shuffled, key=lambda s: s.duration_seconds)
        if shortest.duration_seconds <= max_seconds:
            return [shortest]
        return []

    return selected


def auto_fill_setlist(
    band: Band,
    config: GigConfig,
    *,
    seed: int | None = None,
) -> tuple[list[Song], list[str]]:
    eligible, warnings = filter_songs(band, config)
    picked = pick_songs_for_duration(
        eligible,
        config.duration_minutes,
        config.tolerance_minutes,
        seed=seed,
    )
    if not picked and eligible:
        warnings.append("No songs fit within the target duration window.")
    return picked, warnings
