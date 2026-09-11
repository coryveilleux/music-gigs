#!/usr/bin/env -S uv run --script
"""Import ChordPro charts from CountryTabs for stub charts in a band catalog."""

from __future__ import annotations

import argparse
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from music_gigs.countrytabs import (
    import_tablature_to_chordpro,
    is_chart_stub,
    preserved_chart_comments,
)
from music_gigs.loader import load_song_catalog
from music_gigs.slug import slugify

ROOT = Path(__file__).resolve().parents[1]


def load_chart_sources(band_dir: Path) -> dict[str, dict[str, str]]:
    sources_file = band_dir / "chart-sources.yaml"
    if not sources_file.exists():
        return {}
    with sources_file.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return data.get("sources", {})


def catalog_by_slug(band_dir: Path) -> dict[str, object]:
    catalog = load_song_catalog(band_dir)
    return {slugify(song.title): song for song in catalog.songs}


def stub_slugs(charts_dir: Path) -> list[str]:
    stubs: list[str] = []
    for chart_path in sorted(charts_dir.glob("*.chopro")):
        if is_chart_stub(chart_path):
            stubs.append(chart_path.stem)
    return stubs


def search_countrytabs_url(artist: str, title: str) -> str | None:
    query = urllib.parse.quote_plus(f"site:countrytabs.com {artist} {title} chord tablature")
    url = f"https://html.duckduckgo.com/html/?q={query}"
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    try:
        with urllib.request.urlopen(request, context=context, timeout=20) as response:
            html = response.read().decode("utf-8", errors="replace")
    except OSError:
        return None

    matches = re.findall(r"countrytabs\.com/tablature/[^\"<&]+", html, flags=re.IGNORECASE)
    for match in matches:
        path = urllib.parse.unquote(match)
        if "_Chord_" in path or path.endswith("_Chord/"):
            return f"http://www.{path}" if not path.startswith("http") else path
    return None


def import_song(
    band_dir: Path,
    slug: str,
    sources: dict[str, dict[str, str]],
    songs: dict[str, object],
    *,
    dry_run: bool,
    discover: bool,
) -> str:
    song = songs.get(slug)
    if song is None:
        return f"skip {slug}: not in songs.yaml"

    chart_path = band_dir / "charts" / f"{slug}.chopro"
    force = getattr(import_song, "_force", False)
    if not force and not is_chart_stub(chart_path):
        return f"skip {slug}: chart already filled in"

    source = sources.get(slug, {})
    tab_url = source.get("url")
    if not tab_url and discover:
        tab_url = search_countrytabs_url(song.original_artist, song.title)
        if tab_url:
            print(f"  discovered URL for {slug}: {tab_url}")

    if not tab_url:
        return f"skip {slug}: no URL in chart-sources.yaml"

    if dry_run:
        return f"would import {slug} from {tab_url}"

    extra_comments = preserved_chart_comments(chart_path)
    chordpro = import_tablature_to_chordpro(
        tab_url,
        title=song.title,
        artist=song.original_artist,
        key=song.key,
        source_key=source.get("source_key"),
        extra_comments=extra_comments,
    )
    chart_path.write_text(chordpro, encoding="utf-8")
    return f"imported {slug}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("band_dir", type=Path, help="Band directory (e.g. BailMoneyBand)")
    parser.add_argument("--batch-size", type=int, default=5, help="Max charts per run")
    parser.add_argument("--all", action="store_true", help="Import all stub charts that have URLs")
    parser.add_argument("--slug", action="append", help="Import specific slug(s) only")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be imported")
    parser.add_argument("--force", action="store_true", help="Overwrite existing charts")
    parser.add_argument(
        "--discover-urls",
        action="store_true",
        help="Try DuckDuckGo when chart-sources.yaml has no URL",
    )
    parser.add_argument("--delay", type=float, default=1.5, help="Seconds between fetches")
    args = parser.parse_args()

    band_dir = args.band_dir
    if not band_dir.is_absolute():
        band_dir = ROOT / band_dir

    charts_dir = band_dir / "charts"
    sources = load_chart_sources(band_dir)
    songs = catalog_by_slug(band_dir)

    if args.slug:
        targets = args.slug
    else:
        stubs = stub_slugs(charts_dir)
        with_urls = [slug for slug in stubs if sources.get(slug, {}).get("url")]
        if not with_urls:
            print("No stub charts have URLs in chart-sources.yaml.")
            print("Run: uv run scripts/discover_chart_sources.py BailMoneyBand")
            pending = len(stubs)
            print(f"{pending} stub charts remaining ({pending} without URLs)")
            return
        targets = with_urls

    import_song._force = args.force

    limit = len(targets) if args.all else args.batch_size
    imported = 0
    skipped = 0
    for slug in targets:
        if imported >= limit:
            break
        result = import_song(
            band_dir,
            slug,
            sources,
            songs,
            dry_run=args.dry_run,
            discover=args.discover_urls,
        )
        if result.startswith("imported ") or result.startswith("would import "):
            print(result)
            imported += 1
            if not args.dry_run and imported < limit:
                time.sleep(args.delay)
        elif result.startswith("skip "):
            skipped += 1
        else:
            print(result)

    stubs_remaining = stub_slugs(charts_dir)
    pending = sum(
        1 for slug in stubs_remaining if not sources.get(slug, {}).get("url")
    )
    print(
        f"\n{imported} imported, {skipped} skipped this run. "
        f"{len(stubs_remaining)} stub charts remaining ({pending} without URLs)"
    )


if __name__ == "__main__":
    main()
