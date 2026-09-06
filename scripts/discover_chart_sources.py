#!/usr/bin/env -S uv run --script
"""Discover CountryTabs tablature URLs for stub charts and update chart-sources.yaml."""

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

from music_gigs.countrytabs import extract_pre_html, fetch_tablature, is_chart_stub
from music_gigs.loader import load_song_catalog
from music_gigs.slug import slugify

ROOT = Path(__file__).resolve().parents[1]

# slug -> (search artist, search title)
SEARCH_ALIASES: dict[str, tuple[str, str]] = {
    "folsom": ("Johnny Cash", "Folsom Prison Blues"),
    "wild-knight": ("John Mellencamp", "Wild Night"),
    "beer-with-my-friends": ("Garth Brooks", "Friends in Low Places"),
    "long-live-cow-girls-3-4-scow": ("Ian Munsick", "Long Live Cowgirls"),
    "drink-in-my-hard": ("Eric Church", "Drink In My Hand"),
    "looking-for-love": ("Johnny Lee", "Lookin for Love"),
    "country-ass-shit": ("Morgan Wallen", "Country S**t"),
    "should-a-been-a-cowboy": ("Toby Keith", "Shouldve Been a Cowboy"),
    "much-too-young-to-feel-this-old": ("Garth Brooks", "Much Too Young"),
    "hey-good-lookin": ("Hank Williams", "Hey Good Lookin"),
    "cant-you-see": ("Marshall Tucker Band", "Cant You See"),
    "country-roads": ("John Denver", "Take Me Home Country Roads"),
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
    "fishin-in-the-dark": ("Nitty Gritty Dirt Band", "Fishin In The Dark"),
    "sounds-like-the-radio": ("Zach Top", "Sounds Like The Radio"),
    "open-the-gate": ("Zach Bryan", "Open the Gate"),
    "nine-ball": ("Zach Bryan", "Nine Ball"),
    "american-girl": ("Tom Petty", "American Girl"),
    "mary-jane": ("Tom Petty", "Mary Janes Last Dance"),
    "i-wont-back-down": ("Tom Petty", "I Wont Back Down"),
    "honky-tonk-man": ("Jon Pardi", "Honky Tonk Man"),
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
    "amie": ("Pure Prairie League", "Amie"),
    "sparks-fly": ("Taylor Swift", "Sparks Fly"),
    "all-about-tonight": ("Blake Shelton", "All About Tonight"),
    "pride-and-joy": ("Stevie Ray Vaughan", "Pride And Joy"),
    "beer-in-mexico": ("Kenny Chesney", "Beer In Mexico"),
    "bigfoot": ("Pete Towler", "Bigfoot"),
}


def _ssl_context() -> ssl.SSLContext:
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    return context


def _clean_artist(artist: str) -> str:
    artist = artist.split(" Tribute")[0]
    artist = artist.split(" & ")[0]
    return artist.strip()


def search_countrytabs_url(artist: str, title: str) -> str | None:
    query = urllib.parse.quote_plus(f"site:countrytabs.com/tablature {artist} {title} chord")
    url = f"https://html.duckduckgo.com/html/?q={query}"
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(request, context=_ssl_context(), timeout=25) as response:
            page = response.read().decode("utf-8", errors="replace")
    except OSError:
        return None

    for encoded in re.findall(r"uddg=([^&\"]+)", page):
        link = urllib.parse.unquote(encoded)
        if "countrytabs.com/tablature/" in link and "_Chord_" in link:
            if not link.startswith("http"):
                link = "http://" + link.lstrip("/")
            return link.split("&")[0].rstrip("/") + "/"

    for match in re.findall(r"countrytabs\.com/tablature/[^\"<&]+", page, flags=re.IGNORECASE):
        if "_Chord_" in match:
            return "http://www." + urllib.parse.unquote(match).rstrip("/") + "/"
    return None


def validate_tab_url(url: str) -> bool:
    try:
        extract_pre_html(fetch_tablature(url))
        return True
    except (OSError, ValueError, RuntimeError):
        return False


def load_sources(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return data.get("sources", {})


def save_sources(path: Path, sources: dict[str, dict[str, str]]) -> None:
    header = (
        "# CountryTabs tablature URLs for chart import.\n"
        "# Run: uv run scripts/import_charts_batch.py BailMoneyBand --all\n"
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


def discover_for_slug(
    slug: str,
    artist: str,
    title: str,
    *,
    delay: float,
) -> str | None:
    search_artist, search_title = SEARCH_ALIASES.get(slug, (_clean_artist(artist), title))
    candidates: list[str] = []

    primary = search_countrytabs_url(search_artist, search_title)
    if primary:
        candidates.append(primary)

    if search_title != title:
        secondary = search_countrytabs_url(search_artist, title)
        if secondary and secondary not in candidates:
            candidates.append(secondary)

    if _clean_artist(artist) != search_artist:
        tertiary = search_countrytabs_url(_clean_artist(artist), title)
        if tertiary and tertiary not in candidates:
            candidates.append(tertiary)

    for url in candidates:
        if validate_tab_url(url):
            return url
        time.sleep(delay / 2)

    return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("band_dir", type=Path)
    parser.add_argument("--limit", type=int, default=0, help="Max songs to discover (0 = all)")
    parser.add_argument("--delay", type=float, default=1.0, help="Seconds between searches")
    parser.add_argument("--slug", action="append", help="Discover specific slug(s) only")
    args = parser.parse_args()

    band_dir = args.band_dir
    if not band_dir.is_absolute():
        band_dir = ROOT / band_dir

    sources_path = band_dir / "chart-sources.yaml"
    sources = load_sources(sources_path)
    catalog = {slugify(s.title): s for s in load_song_catalog(band_dir).songs}

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

        url = discover_for_slug(slug, song.original_artist, song.title, delay=args.delay)
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
