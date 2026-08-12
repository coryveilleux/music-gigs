"""Tests for music_gigs core logic."""

from pathlib import Path

import pytest

from music_gigs.loader import discover_bands
from music_gigs.models import GigConfig
from music_gigs.orderer import build_setlist, check_constraints, num_sets_for_duration
from music_gigs.picker import auto_fill_setlist, filter_songs


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def band():
    bands = discover_bands(ROOT)
    assert bands
    return bands[0]


def test_discover_bands(band):
    assert band.name == "The Otters"
    assert len(band.catalog.songs) >= 1


def test_filter_excludes_absent_singer(band):
    config = GigConfig(absent_members=["singer1"])
    eligible, _ = filter_songs(band, config)
    assert all(s.lead_singer != "singer1" for s in eligible)


def test_auto_fill_respects_duration(band):
    config = GigConfig(duration_minutes=30, tolerance_minutes=5)
    picked, _ = auto_fill_setlist(band, config, seed=1)
    total = sum(s.duration_seconds for s in picked)
    assert total <= 35 * 60


def test_num_sets_for_duration():
    assert num_sets_for_duration(90) == 1
    assert num_sets_for_duration(120) == 2


def test_build_setlist_no_duplicate_positions(band):
    config = GigConfig(duration_minutes=90)
    picked, warnings = auto_fill_setlist(band, config, seed=42)
    setlist = build_setlist(band, picked, 90, warnings, seed=42)
    assert setlist.songs
    positions = [(s.set_number, s.position) for s in setlist.songs]
    assert len(positions) == len(set(positions))


def test_constraint_check_detects_same_artist_back_to_back(band):
    songs = band.catalog.songs[:2]
    if len(songs) == 2:
        same_artist = [songs[0], songs[0]]
        warnings = check_constraints(same_artist, 1)
        assert any(w.rule == "original_artist" for w in warnings)
