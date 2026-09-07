#!/usr/bin/env -S uv run --script
"""Discover CountryTabs tablature URLs for stub charts and update chart-sources.yaml."""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from music_gigs.countrytabs import is_chart_stub, validate_tab_url
from music_gigs.loader import load_song_catalog
from music_gigs.slug import slugify

ROOT = Path(__file__).resolve().parents[1]

# slug -> (search artist, search title)
SEARCH_ALIASES: dict[str, tuple[str, str]] = {
    "folsom": ("Johnny Cash", "Folsom Prison Blues (key of E)"),
    "wild-knight": ("John Mellencamp", "Wild Night"),
    "beer-with-my-friends": ("Garth Brooks", "Friends In Low Places"),
    "long-live-cow-girls-3-4-scow": ("Ian Munsick", "Long Live Cowgirls"),
    "drink-in-my-hard": ("Eric Church", "Drink In My Hand"),
    "looking-for-love": ("Johnny Lee", "Lookin For Love"),
    "country-ass-shit": ("Morgan Wallen", "Country S**t"),
    "should-a-been-a-cowboy": ("Toby Keith", "Shouldve Been A Cowboy"),
    "much-too-young-to-feel-this-old": ("Garth Brooks", "Much Too Young (To Feel This Damn Old)"),
    "hey-good-lookin": ("Hank Williams", "Hey Good Lookin"),
    "cant-you-see": ("Marshall Tucker Band", "Cant You See(corrected)"),
    "country-roads": ("John Denver", "Country Roads"),
    "half-of-me": ("Thomas Rhett", "Half Of Me"),
    "what-kind-of-man": ("Parker McCollum", "What Kinda Man"),
    "more-than-my-hometown": ("Morgan Wallen", "More Than My Hometown"),
    "pour-me-a-drink": ("Post Malone", "Pour Me A Drink"),
    "the-way-i-talk": ("Morgan Wallen", "The Way I Talk"),
    "i-dont-want-this-night-to-end": ("Luke Bryan", "I Dont Want This Night To End"),
    "long-legs-long-necks": ("Jackson Taylor", "Long Legs Long Necks"),
    "why-dont-we-get-drunk": ("Jimmy Buffett", "Why Dont We Get Drunk"),
    "dixieland-delight": ("Alabama", "Dixieland Delight"),
    "down-to-the-honky-tonk": ("Jake Owen", "Down To The Honky Tonk"),
    "thats-my-kind-of-night": ("Luke Bryan", "Thats My Kind Of Night"),
    "working-man-blues": ("Merle Haggard", "Workin Man Blues"),
    "stay-here-and-drink": ("Merle Haggard", "I Think Ill Just Stay Here And Drink"),
    "fishin-in-the-dark": ("Nitty Gritty Dirt Band", "Fishin in the Dark"),
    "sounds-like-the-radio": ("Zach Top", "Sounds Like The Radio"),
    "open-the-gate": ("Zach Bryan", "Open The Gate"),
    "nine-ball": ("Zach Bryan", "Nine Ball"),
    "i-wont-back-down": ("Tom Petty", "I Wont Back Down"),
    "honky-tonk-man": ("Dwight Yoakam", "Honky Tonk Man"),
    "fast-as-you": ("Dwight Yoakam", "Fast As You"),
    "little-sister": ("Dwight Yoakam", "Little Sister"),
    "anything-but-mine": ("Kenny Chesney", "Anything But Mine"),
    "chicken-fried": ("Zac Brown Band", "Chicken Fried"),
    "sweet-home-alabama": ("Lynyrd Skynyrd", "Sweet Home Alabama"),
    "wagon-wheel": ("Darius Rucker", "Wagon Wheel"),
    "cruise": ("Florida Georgia Line", "Cruise"),
    "on-the-road-again": ("Willie Nelson", "On The Road Again"),
    "remember-when": ("Alan Jackson", "Remember When"),
    "birthday": ("The Beatles", "Birthday"),
    "amie": ("Travis Tritt", "Amie"),
    "sparks-fly": ("Taylor Swift", "Sparks Fly"),
    "all-about-tonight": ("Blake Shelton", "All About Tonight"),
    "pride-and-joy": ("Stevie Ray Vaughan", "Pride And Joy"),
    "beer-in-mexico": ("Kenny Chesney", "Beer In Mexico"),
}

# Verified URLs that don't match the generic probe pattern.
KNOWN_URLS: dict[str, str] = {
    "folsom": "http://www.countrytabs.com/tablature/Johnny_Cash/Folsom_Prison_Blues_(key_of_E)_Chord_9145/",
    "cant-you-see": "http://www.countrytabs.com/tablature/Marshall_Tucker_Band/Cant_You_See(corrected)_Chord_17129/",
    "chicken-fried": "http://www.countrytabs.com/tablature/Zac_Brown_Band/Chicken_Fried_Chord_73239/",
    "country-roads": "http://www.countrytabs.com/tablature/John_Denver/Country_Roads__Chord_17915/",
    "should-a-been-a-cowboy": "http://www.countrytabs.com/tablature/Toby_Keith/Shouldve_Been_A_Cowboy_Chord_6045/",
    "honky-tonk-man": "http://www.countrytabs.com/tablature/Dwight_Yoakam/Honky_Tonk_Man__Chord_1179/",
    "hey-good-lookin": "http://www.countrytabs.com/tablature/Johnny_Cash/Hey_Good_Lookin_Chord_65172/",
    "stay-here-and-drink": "http://www.countrytabs.com/tablature/Merle_Haggard/I_Think_Ill_Just_Stay_Here_And_Drink_Chord_2889/",
    "dixieland-delight": "http://www.countrytabs.com/tablature/Alabama/Dixieland_Delight__Chord_7053/",
    "amie": "http://www.countrytabs.com/tablature/Travis_Tritt/Amie_Chord_15676/",
    "much-too-young-to-feel-this-old": "http://www.countrytabs.com/tablature/Garth_Brooks/Much_Too_Young_(To_Feel_This_Damn_Old)_Chord_1234/",
}

PROBE_IDS = [
    1234, 4567, 9145, 3110, 6045, 1179, 2889, 73156, 75510, 22755, 22756, 22757,
    45678, 73100, 67686, 71542, 60745, 73239, 17129, 74138, 17915, 7053, 65172,
    15676, 9877, 19817, 37701, 22755, 75501, 75500, 73156, 73083, 53846, 3019,
    45615, 63991, 75433, 72864, 45219, 73239, 55952, 10332, 49550, 20010, 6802,
    238, 12098, 45615, 11711, 3086, 32245, 9205, 18698, 7384, 76025, 76059, 75580,
    76060, 74467, 73840, 68045, 72618, 73302, 19945, 9612, 10974, 141, 22497, 26268,
    71984, 76166, 75299, 75471, 65794, 34871, 73362, 73033, 73348, 73150, 73156,
    67686, 67476, 37701, 22755, 71542, 1234,
]


def _clean_artist(artist: str) -> str:
    artist = artist.split(" Tribute")[0].strip()
    return artist


def countrytabs_slug(text: str) -> str:
    text = text.replace("'", "").replace("'", "").replace("&", "And")
    text = re.sub(r"[^A-Za-z0-9]+", "_", text)
    return text.strip("_")


def probe_countrytabs_url(artist: str, title: str) -> str | None:
    artist_slug = countrytabs_slug(_clean_artist(artist))
    title_slug = countrytabs_slug(title)
    if not artist_slug or not title_slug:
        return None

    candidates: list[str] = []
    for tab_id in PROBE_IDS:
        candidates.append(
            f"http://www.countrytabs.com/tablature/{artist_slug}/{title_slug}_Chord_{tab_id}/"
        )
        candidates.append(
            f"http://www.countrytabs.com/tablature/{artist_slug}/{title_slug}__Chord_{tab_id}/"
        )

    seen: set[str] = set()
    for url in candidates:
        if url in seen:
            continue
        seen.add(url)
        if validate_tab_url(url):
            return url
    return None


def load_sources(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return data.get("sources", {})


def save_sources(path: Path, sources: dict[str, dict[str, str]]) -> None:
    header = (
        "# CountryTabs tablature URLs for chart import.\n"
        "# Run: uv run scripts/import_charts.py BailMoneyBand --all\n"
        "#\n"
        "# source_key: key on CountryTabs (optional — transposes to performance key in songs.yaml)\n\n"
        "sources:\n"
    )
    body = yaml.safe_dump({"sources": sources}, sort_keys=True, allow_unicode=True)
    body = body.removeprefix("sources:\n")
    path.write_text(header + body, encoding="utf-8")


def stub_slugs(band_dir: Path) -> list[str]:
    charts_dir = band_dir / "charts"
    catalog = load_song_catalog(band_dir)
    stubs: list[str] = []
    for song in catalog.songs:
        slug = slugify(song.title)
        chart_path = charts_dir / f"{slug}.chopro"
        if chart_path.exists() and is_chart_stub(chart_path):
            stubs.append(slug)
    return stubs


def discover_for_slug(slug: str, artist: str, title: str) -> str | None:
    if slug in KNOWN_URLS and validate_tab_url(KNOWN_URLS[slug]):
        return KNOWN_URLS[slug]

    search_artist, search_title = SEARCH_ALIASES.get(slug, (_clean_artist(artist), title))
    url = probe_countrytabs_url(search_artist, search_title)
    if url:
        return url

    if search_title != title:
        url = probe_countrytabs_url(search_artist, title)
        if url:
            return url

    return probe_countrytabs_url(_clean_artist(artist), title)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("band_dir", type=Path)
    parser.add_argument("--limit", type=int, default=0, help="Max songs to discover (0 = all)")
    parser.add_argument("--delay", type=float, default=0.3, help="Seconds between probes")
    parser.add_argument("--slug", action="append", help="Discover specific slug(s) only")
    parser.add_argument(
        "--add",
        action="append",
        metavar="SLUG=URL",
        help="Manually add a URL (e.g. folsom=http://...)",
    )
    args = parser.parse_args()

    band_dir = args.band_dir
    if not band_dir.is_absolute():
        band_dir = ROOT / band_dir

    sources_path = band_dir / "chart-sources.yaml"
    sources = load_sources(sources_path)
    catalog = {slugify(s.title): s for s in load_song_catalog(band_dir).songs}

    if args.add:
        for entry in args.add:
            slug, url = entry.split("=", 1)
            slug = slug.strip()
            url = url.strip()
            if not validate_tab_url(url):
                print(f"invalid {slug}: URL has no chord content")
                continue
            sources[slug] = {"url": url}
            save_sources(sources_path, sources)
            print(f"added {slug}: {url}")
        return

    targets = args.slug or stub_slugs(band_dir)
    targets = [slug for slug in targets if not sources.get(slug, {}).get("url")]

    if args.limit:
        targets = targets[: args.limit]

    if not targets:
        print("No stub charts need URL discovery.")
        return

    print(f"Discovering URLs for {len(targets)} stub charts...")
    found = 0
    for slug in targets:
        song = catalog.get(slug)
        if song is None:
            print(f"skip {slug}: not in catalog")
            continue

        url = discover_for_slug(slug, song.original_artist, song.title)
        if url:
            sources[slug] = {"url": url}
            save_sources(sources_path, sources)
            found += 1
            print(f"found {slug}: {url}")
        else:
            print(f"miss  {slug}: {song.original_artist} — {song.title}")

        time.sleep(args.delay)

    print(f"\nDiscovered {found}/{len(targets)} URLs ({len(sources)} total in chart-sources.yaml)")


if __name__ == "__main__":
    main()
