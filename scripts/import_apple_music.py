#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "pyyaml>=6.0.0",
#     "pydantic>=2.0.0",
# ]
# ///
"""Import songs from an Apple Music playlist export (TSV or Library XML)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

# Allow running from repo root or as installed package
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from music_gigs.apple_music import parse_playlist
from music_gigs.loader import load_band_config, load_song_catalog
from music_gigs.models import Song


def _prompt_yes_no(prompt: str, default: bool = True) -> bool:
    suffix = "[Y/n]" if default else "[y/N]"
    answer = input(f"{prompt} {suffix} ").strip().lower()
    if not answer:
        return default
    return answer in ("y", "yes")


def _prompt_choice(prompt: str, options: list[tuple[str, str]]) -> str:
    print(prompt)
    for i, (opt_id, label) in enumerate(options, start=1):
        print(f"  {i}. {label} ({opt_id})")
    while True:
        answer = input("Choice: ").strip()
        if answer.isdigit():
            idx = int(answer) - 1
            if 0 <= idx < len(options):
                return options[idx][0]
        for opt_id, label in options:
            if answer.lower() in (opt_id.lower(), label.lower()):
                return opt_id
        print("Invalid choice, try again.")


def _prompt_key(default: str = "C") -> str:
    answer = input(f"Key [{default}]: ").strip()
    return answer or default


def _track_key(title: str, artist: str) -> tuple[str, str]:
    return title.lower(), artist.lower()


def import_playlist(playlist_path: Path, band_dir: Path, batch_size: int = 10) -> None:
    band_config = load_band_config(band_dir)
    catalog = load_song_catalog(band_dir)
    existing = {_track_key(s.title, s.original_artist) for s in catalog.songs}

    try:
        tracks = parse_playlist(playlist_path)
    except ValueError as exc:
        print(f"Error: {exc}")
        sys.exit(1)

    if not tracks:
        print("No tracks found in playlist.")
        return

    members = [(m.id, m.name) for m in band_config.members]
    if not members:
        print("Error: band.yaml has no members. Add members before importing.")
        sys.exit(1)

    new_songs: list[Song] = []
    skipped = 0

    for batch_start in range(0, len(tracks), batch_size):
        batch = tracks[batch_start : batch_start + batch_size]
        print(f"\n--- Songs {batch_start + 1}–{batch_start + len(batch)} of {len(tracks)} ---\n")

        for track in batch:
            print(
                f"\n{track.title} — {track.artist} "
                f"({track.duration_seconds // 60}:{track.duration_seconds % 60:02d})"
            )
            if track.album:
                print(f"  Album: {track.album}")
            if track.writers:
                print(f"  Writers: {', '.join(track.writers)}")

            if _track_key(track.title, track.artist) in existing:
                print("  Already in catalog, skipping.")
                skipped += 1
                continue

            if not _prompt_yes_no("  Include this song?", default=True):
                skipped += 1
                continue

            lead_singer = _prompt_choice("  Lead singer:", members)
            key = _prompt_key()

            song = Song(
                title=track.title,
                original_artist=track.artist,
                key=key,
                lead_singer=lead_singer,
                duration_seconds=track.duration_seconds or 180,
                active=True,
                writers=track.writers,
            )
            new_songs.append(song)
            existing.add(_track_key(track.title, track.artist))
            print(f"  Added: {song.title}")

    if not new_songs:
        print(f"\nNo new songs added ({skipped} skipped).")
        return

    catalog.songs.extend(new_songs)
    songs_file = band_dir / "songs.yaml"
    with songs_file.open("w", encoding="utf-8") as f:
        yaml.dump(
            {"songs": [s.model_dump(exclude_none=True) for s in catalog.songs]},
            f,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )

    print(f"\nAdded {len(new_songs)} songs to {songs_file} ({skipped} skipped).")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import songs from an Apple Music playlist export into a band catalog."
    )
    parser.add_argument(
        "playlist_path",
        type=Path,
        help="Path to Apple Music playlist export (.txt TSV or Library .xml)",
    )
    parser.add_argument("band_dir", type=Path, help="Band directory (e.g. TheOtters)")
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10,
        help="Number of songs to prompt per batch (default: 10)",
    )
    args = parser.parse_args()

    if not args.playlist_path.exists():
        print(f"Error: {args.playlist_path} not found")
        sys.exit(1)
    if not args.band_dir.is_dir():
        print(f"Error: {args.band_dir} is not a directory")
        sys.exit(1)

    import_playlist(args.playlist_path, args.band_dir, batch_size=args.batch_size)


if __name__ == "__main__":
    main()
