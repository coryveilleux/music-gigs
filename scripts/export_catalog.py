#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "pydantic>=2.0.0",
#     "pyyaml>=6.0.0",
#     "fpdf2>=2.8.0",
# ]
# ///
"""Export the full song catalog as an aligned review list."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from music_gigs.export import render_catalog_review, render_catalog_review_pdf
from music_gigs.loader import load_band


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export song catalog as aligned singer - key - title: artist list."
    )
    parser.add_argument("band_dir", type=Path, help="Band directory (e.g. TheOtters)")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Write to file instead of stdout (use .pdf for PDF output)",
    )
    parser.add_argument(
        "--pdf",
        action="store_true",
        help="Export as PDF (or inferred when -o ends with .pdf)",
    )
    parser.add_argument(
        "--include-inactive",
        action="store_true",
        help="Include songs marked active: false",
    )
    args = parser.parse_args()

    if not args.band_dir.is_dir():
        print(f"Error: {args.band_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    band = load_band(args.band_dir)
    active_only = not args.include_inactive
    as_pdf = args.pdf or (args.output is not None and args.output.suffix.lower() == ".pdf")

    if as_pdf:
        pdf_bytes = render_catalog_review_pdf(band, active_only=active_only)
        if args.output:
            args.output.write_bytes(pdf_bytes)
            print(f"Wrote PDF ({len(pdf_bytes) // 1024} KB) to {args.output}")
        else:
            sys.stdout.buffer.write(pdf_bytes)
        return

    text = render_catalog_review(band, active_only=active_only)
    if args.output:
        args.output.write_text(text, encoding="utf-8")
        print(f"Wrote {len(text.splitlines())} songs to {args.output}")
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    main()
