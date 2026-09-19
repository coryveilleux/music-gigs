#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "pydantic>=2.0.0",
#     "pyyaml>=6.0.0",
#     "fpdf2>=2.8.0",
# ]
# ///
"""Build a printable PDF gig book from a band set list."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from music_gigs.gig_html import build_gig_data
from music_gigs.gig_pdf import render_gig_pdf


def pdf_page_count(pdf_bytes: bytes) -> int:
    return len(re.findall(rb"/Type\s*/Page\b", pdf_bytes))


def main() -> None:
    parser = argparse.ArgumentParser(description="Build gig PDF from set list + ChordPro charts.")
    parser.add_argument("band_dir", type=Path, help="Band directory (e.g. BailMoneyBand)")
    parser.add_argument("set_file", type=Path, help="Set YAML (e.g. sets/stone-cow-2026-09-19.yaml)")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output PDF path (default: band_dir/gigs/<set-stem>.pdf)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        metavar="N",
        help="Include only the first N songs (for prototypes)",
    )
    args = parser.parse_args()

    band_dir = args.band_dir
    set_path = args.set_file
    if not set_path.is_absolute():
        set_path = band_dir / set_path

    if not band_dir.is_dir():
        print(f"Error: {band_dir} is not a directory", file=sys.stderr)
        sys.exit(1)
    if not set_path.exists():
        print(f"Error: {set_path} not found", file=sys.stderr)
        sys.exit(1)

    output = args.output or (band_dir / "gigs" / f"{set_path.stem}.pdf")
    gig_data = build_gig_data(band_dir, set_path)
    for song in gig_data["songs"]:
        for warning in song.get("chart_warnings", []):
            print(f"Warning: {warning}", file=sys.stderr)

    pdf_bytes = render_gig_pdf(gig_data, song_limit=args.limit)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(pdf_bytes)

    included = args.limit if args.limit else len(gig_data["songs"])
    print(f"Wrote {output} ({included} songs, {pdf_page_count(pdf_bytes)} pages)")


if __name__ == "__main__":
    main()
