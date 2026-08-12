from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from music_gigs.models import Band, BandConfig, Song, SongCatalog


def _slug_from_directory(directory_name: str) -> str:
    return directory_name.lower().replace("_", "-")


def load_band_config(band_dir: Path) -> BandConfig:
    band_file = band_dir / "band.yaml"
    if not band_file.exists():
        raise FileNotFoundError(f"Missing band.yaml in {band_dir}")
    with band_file.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return BandConfig.model_validate(data)


def load_song_catalog(band_dir: Path) -> SongCatalog:
    songs_file = band_dir / "songs.yaml"
    if not songs_file.exists():
        raise FileNotFoundError(f"Missing songs.yaml in {band_dir}")
    with songs_file.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return SongCatalog.model_validate(data)


def load_band(band_dir: Path) -> Band:
    directory = band_dir.name
    config = load_band_config(band_dir)
    catalog = load_song_catalog(band_dir)
    slug = config.slug or _slug_from_directory(directory)
    return Band(directory=directory, slug=slug, config=config, catalog=catalog)


def discover_bands(root: Path) -> list[Band]:
    bands: list[Band] = []
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        if child.name.startswith(".") or child.name in {"src", "apps", "scripts", ".venv"}:
            continue
        if not (child / "songs.yaml").exists():
            continue
        try:
            bands.append(load_band(child))
        except (FileNotFoundError, ValidationError):
            continue
    return bands


def validate_song_members(band: Band) -> list[str]:
    member_ids = {member.id for member in band.config.members}
    warnings: list[str] = []
    for song in band.catalog.songs:
        if song.lead_singer not in member_ids:
            warnings.append(
                f'"{song.title}" has unknown lead_singer "{song.lead_singer}"'
            )
    return warnings


def format_duration(seconds: int) -> str:
    minutes, secs = divmod(seconds, 60)
    return f"{minutes}:{secs:02d}"
