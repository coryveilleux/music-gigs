from __future__ import annotations

import math
import random
from collections import defaultdict
from typing import TYPE_CHECKING

from music_gigs.models import ConstraintWarning, SetList, SetListSong, Song

if TYPE_CHECKING:
    from music_gigs.models import Band


def num_sets_for_duration(duration_minutes: int) -> int:
    if duration_minutes <= 90:
        return 1
    return max(1, math.ceil(duration_minutes / 60))


def split_into_sets(songs: list[Song], duration_minutes: int) -> dict[int, list[Song]]:
    """Assign songs to sets, balancing by duration via round-robin."""
    if not songs:
        return {}

    num_sets = num_sets_for_duration(duration_minutes)
    sets: dict[int, list[Song]] = {i: [] for i in range(1, num_sets + 1)}
    set_durations: dict[int, int] = defaultdict(int)

    sorted_songs = sorted(songs, key=lambda s: s.duration_seconds, reverse=True)
    for song in sorted_songs:
        target_set = min(
            range(1, num_sets + 1),
            key=lambda n: set_durations[n],
        )
        sets[target_set].append(song)
        set_durations[target_set] += song.duration_seconds

    return sets


def _count_consecutive(values: list[str], max_allowed: int) -> list[tuple[int, int]]:
    """Return (start_index, run_length) for runs exceeding max_allowed."""
    violations: list[tuple[int, int]] = []
    if not values:
        return violations

    run_start = 0
    for i in range(1, len(values) + 1):
        if i == len(values) or values[i] != values[run_start]:
            run_len = i - run_start
            if run_len > max_allowed:
                violations.append((run_start, run_len))
            run_start = i
    return violations


def check_constraints(songs: list[Song], set_number: int) -> list[ConstraintWarning]:
    warnings: list[ConstraintWarning] = []

    singers = [s.lead_singer for s in songs]
    for start, length in _count_consecutive(singers, 2):
        warnings.append(
            ConstraintWarning(
                rule="lead_singer",
                message=f"{length} consecutive songs by the same lead singer",
                set_number=set_number,
                song_indices=list(range(start, start + length)),
            )
        )

    artists = [s.original_artist for s in songs]
    for start, length in _count_consecutive(artists, 1):
        warnings.append(
            ConstraintWarning(
                rule="original_artist",
                message="Back-to-back songs by the same original artist",
                set_number=set_number,
                song_indices=list(range(start, start + length)),
            )
        )

    keys = [s.key for s in songs]
    for start, length in _count_consecutive(keys, 2):
        warnings.append(
            ConstraintWarning(
                rule="key",
                message=f"{length} consecutive songs in the same key",
                set_number=set_number,
                song_indices=list(range(start, start + length)),
            )
        )

    return warnings


def _try_swap_to_fix(songs: list[Song], max_iterations: int = 500) -> list[Song]:
    """Reorder songs via adjacent swaps to reduce constraint violations."""
    result = songs.copy()
    if len(result) < 2:
        return result

    for _ in range(max_iterations):
        warnings = check_constraints(result, 1)
        if not warnings:
            break

        warning = warnings[0]
        indices = warning.song_indices
        if not indices:
            break

        swap_idx = indices[-1]
        swapped = False
        for offset in (1, -1, 2, -2):
            target = swap_idx + offset
            if 0 <= target < len(result):
                result[swap_idx], result[target] = result[target], result[swap_idx]
                swapped = True
                break
        if not swapped:
            break

    return result


def order_set(songs: list[Song], *, seed: int | None = None) -> list[Song]:
    if len(songs) <= 1:
        return songs.copy()

    rng = random.Random(seed)
    ordered = songs.copy()
    rng.shuffle(ordered)
    return _try_swap_to_fix(ordered)


def build_setlist(
    band: Band,
    songs: list[Song],
    duration_minutes: int,
    filter_warnings: list[str] | None = None,
    *,
    seed: int | None = None,
) -> SetList:
    filter_warnings = filter_warnings or []
    set_groups = split_into_sets(songs, duration_minutes)

    entries: list[SetListSong] = []
    all_warnings: list[ConstraintWarning] = []

    for set_number in sorted(set_groups):
        ordered = order_set(set_groups[set_number], seed=seed)
        all_warnings.extend(check_constraints(ordered, set_number))
        for position, song in enumerate(ordered, start=1):
            entries.append(
                SetListSong(song=song, set_number=set_number, position=position)
            )

    return SetList(
        songs=entries,
        warnings=all_warnings,
        filter_warnings=filter_warnings,
    )


def reorder_setlist(
    band: Band,
    song_titles: list[str],
    set_numbers: list[int],
    duration_minutes: int,
) -> SetList:
    """Rebuild a set list from manual ordering (by title + set number)."""
    title_to_song = {s.title: s for s in band.catalog.songs}
    entries: list[SetListSong] = []
    warnings: list[ConstraintWarning] = []

    set_positions: dict[int, int] = defaultdict(int)
    for title, set_number in zip(song_titles, set_numbers, strict=True):
        song = title_to_song.get(title)
        if not song:
            continue
        set_positions[set_number] += 1
        entries.append(
            SetListSong(
                song=song,
                set_number=set_number,
                position=set_positions[set_number],
            )
        )

    for set_number in sorted({e.set_number for e in entries}):
        set_songs = [e.song for e in entries if e.set_number == set_number]
        warnings.extend(check_constraints(set_songs, set_number))

    return SetList(songs=entries, warnings=warnings)
