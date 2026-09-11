#!/usr/bin/env -S uv run --script
"""Re-fetch and restructure CountryTabs charts into sectioned ChordPro.

Use this after import when charts are one big block (or need better sections).
Skips charts you've finished (those with a Structure comment) unless --force-slug.

Examples:
  # Gig setlist charts — skip Buy Me a Boat and other finished charts
  uv run scripts/restructure_charts.py BailMoneyBand --set sets/lilac-hedge-farm-2026-09-12.yaml

  # One song
  uv run scripts/restructure_charts.py BailMoneyBand --slug folsom --force

  # Everything in catalog that looks imported (slow — many network requests)
  uv run scripts/restructure_charts.py BailMoneyBand --all --batch-size 10
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from music_gigs.chart_sections import chart_content_matches
from music_gigs.countrytabs import import_tablature_to_chordpro, preserved_chart_comments
from music_gigs.loader import load_song_catalog
from music_gigs.slug import slugify

ROOT = Path(__file__).resolve().parents[1]
_STRUCTURE_RE = re.compile(r"^\{comment:\s*structure:", re.IGNORECASE)
_IMPORTED_RE = re.compile(r"imported from countrytabs", re.IGNORECASE)


def load_chart_sources(band_dir: Path) -> dict[str, dict[str, str]]:
    path = band_dir / "chart-sources.yaml"
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return data.get("sources", {})


def load_set_slugs(band_dir: Path, set_path: Path) -> list[str]:
    with set_path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    slugs: list[str] = []
    for set_block in data.get("sets", []):
        for entry in set_block.get("songs", []):
            if isinstance(entry, str):
                slugs.append(entry)
            elif isinstance(entry, dict) and entry.get("slug"):
                slugs.append(entry["slug"])
    return slugs


def is_chart_complete(chart_path: Path) -> bool:
    """Charts you've curated — skip unless --force."""
    if not chart_path.exists():
        return False
    text = chart_path.read_text(encoding="utf-8")
    lowered = text.lower()
    if "chart complete" in lowered:
        return True
    if "<<" in text and ">>" in text:
        return True
    structure_match = re.search(r"\{comment:\s*Structure:\s*([^}]+)\}", text, re.IGNORECASE)
    if structure_match and re.search(r"\d", structure_match.group(1)):
        return True
    if "Imported from CountryTabs" not in text:
        if _STRUCTURE_RE.search(text) or "{c:" in text:
            return True
    return False


def is_countrytabs_import(chart_path: Path) -> bool:
    if not chart_path.exists():
        return False
    return bool(_IMPORTED_RE.search(chart_path.read_text(encoding="utf-8").lower()))


def restructure_slug(
    band_dir: Path,
    slug: str,
    sources: dict[str, dict[str, str]],
    songs: dict[str, object],
    *,
    dry_run: bool,
    force: bool,
) -> str:
    song = songs.get(slug)
    if song is None:
        return f"skip {slug}: not in songs.yaml"

    chart_path = band_dir / "charts" / f"{slug}.chopro"
    if chart_path.exists() and is_chart_complete(chart_path) and not force:
        return f"skip {slug}: chart marked complete (Structure comment)"

    source = sources.get(slug, {})
    tab_url = source.get("url")
    if not tab_url:
        return f"skip {slug}: no URL in chart-sources.yaml"

    if dry_run:
        return f"would restructure {slug} from {tab_url}"

    from music_gigs.countrytabs import extract_pre_html, fetch_tablature, pre_html_to_lines

    page = fetch_tablature(tab_url)
    lines = pre_html_to_lines(extract_pre_html(page))
    if not chart_content_matches(song.title, lines):
        return (
            f"skip {slug}: CountryTabs page does not look like “{song.title}” "
            f"(wrong URL?) — {tab_url}"
        )

    extra_comments = preserved_chart_comments(chart_path)
    chordpro = import_tablature_to_chordpro(
        tab_url,
        title=song.title,
        artist=song.original_artist,
        key=song.key,
        source_key=source.get("source_key"),
        extra_comments=extra_comments,
        add_structure_comment=True,
    )
    chart_path.write_text(chordpro, encoding="utf-8")
    section_count = chordpro.count("{start_of_")
    return f"restructured {slug} ({section_count} sections)"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("band_dir", type=Path, help="Band directory (e.g. BailMoneyBand)")
    parser.add_argument("--set", type=Path, help="Setlist YAML — only restructure those songs")
    parser.add_argument("--slug", action="append", help="Specific slug(s) only")
    parser.add_argument("--all", action="store_true", help="All catalog songs with CountryTabs URLs")
    parser.add_argument(
        "--imported-only",
        action="store_true",
        help="With --all, only charts previously imported from CountryTabs",
    )
    parser.add_argument("--batch-size", type=int, default=15, help="Max charts per run")
    parser.add_argument("--force", action="store_true", help="Overwrite even complete charts")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--delay", type=float, default=1.2, help="Seconds between fetches")
    args = parser.parse_args()

    band_dir = args.band_dir
    if not band_dir.is_absolute():
        band_dir = ROOT / band_dir

    sources = load_chart_sources(band_dir)
    catalog = load_song_catalog(band_dir)
    songs = {slugify(song.title): song for song in catalog.songs}
    charts_dir = band_dir / "charts"

    if args.slug:
        targets = args.slug
    elif args.set:
        set_path = args.set if args.set.is_absolute() else band_dir / args.set
        targets = load_set_slugs(band_dir, set_path)
    elif args.all:
        targets = sorted(songs)
        if args.imported_only:
            targets = [
                slug
                for slug in targets
                if is_countrytabs_import(charts_dir / f"{slug}.chopro")
            ]
    else:
        parser.error("Specify --set, --slug, or --all")

    limit = len(targets) if (args.all or args.set) else args.batch_size
    done = 0
    for slug in targets:
        if done >= limit:
            break
        if not sources.get(slug, {}).get("url"):
            print(f"skip {slug}: no URL in chart-sources.yaml")
            continue
        result = restructure_slug(
            band_dir,
            slug,
            sources,
            songs,
            dry_run=args.dry_run,
            force=args.force,
        )
        print(result)
        if result.startswith("restructured ") or result.startswith("would restructure "):
            done += 1
            if not args.dry_run and done < limit:
                time.sleep(args.delay)

    print(f"\nDone. {done} chart(s) processed this run.")


if __name__ == "__main__":
    main()
