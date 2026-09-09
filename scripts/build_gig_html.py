#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "pydantic>=2.0.0",
#     "pyyaml>=6.0.0",
# ]
# ///
"""Build a single-file HTML gig book from a band set list."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from music_gigs.gig_html import build_gig_data, render_gig_html


def main() -> None:
    parser = argparse.ArgumentParser(description="Build offline gig HTML from set list + ChordPro charts.")
    parser.add_argument("band_dir", type=Path, help="Band directory (e.g. BailMoneyBand)")
    parser.add_argument("set_file", type=Path, help="Set YAML (e.g. sets/pilot-gig.yaml)")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output HTML path (default: band_dir/gig.html)",
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
        print(f"Error: {set_path} not found", sys.stderr)
        sys.exit(1)

    output = args.output or (band_dir / "gig.html")
    gig_data = build_gig_data(band_dir, set_path)
    for song in gig_data["songs"]:
        for warning in song.get("chart_warnings", []):
            print(f"Warning: {warning}", file=sys.stderr)
    html = render_gig_html(gig_data)
    output.write_text(html, encoding="utf-8")
    print(f"Wrote {output} ({len(gig_data['songs'])} songs, {len(gig_data['sets'])} sets)")


if __name__ == "__main__":
    main()
