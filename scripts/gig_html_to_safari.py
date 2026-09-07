#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# ///
"""Copy a gig HTML file to the clipboard as a data: URI for Safari on iOS."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from music_gigs.gig_html import html_to_data_uri


def copy_to_clipboard(text: str) -> None:
    if not shutil.which("pbcopy"):
        raise RuntimeError("pbcopy not found (macOS clipboard). Use --print instead.")
    subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Encode gig HTML as a data: URI and copy to the clipboard for Safari on iOS "
            "(via Universal Clipboard)."
        )
    )
    parser.add_argument("html_file", type=Path, help="Gig HTML file (from build_gig_html.py)")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Also write the data: URI to a text file",
    )
    parser.add_argument(
        "--print",
        action="store_true",
        help="Print the data: URI to stdout instead of copying",
    )
    args = parser.parse_args()

    html_path = args.html_file.resolve()
    if not html_path.is_file():
        print(f"Error: {html_path} not found", file=sys.stderr)
        sys.exit(1)

    html_bytes = html_path.read_bytes()
    uri = html_to_data_uri(html_bytes)
    uri_kb = len(uri) // 1024
    html_kb = len(html_bytes) // 1024

    print(f"HTML: {html_kb:,} KB → data URI: {uri_kb:,} KB ({len(uri):,} characters)")

    if uri_kb > 2_000:
        print(
            "Warning: very large URI — Safari may refuse to load it. "
            "Try a shorter set list if paste/navigation fails.",
            file=sys.stderr,
        )
    elif uri_kb > 1_000:
        print(
            "Note: large URI — allow a few seconds for Safari to load after pasting.",
            file=sys.stderr,
        )

    if args.output:
        args.output.write_text(uri, encoding="utf-8")
        print(f"Wrote {args.output}")

    if args.print:
        print(uri)
        return

    try:
        copy_to_clipboard(uri)
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    print("Copied to clipboard.")
    print("On iPhone: open Safari → tap the address bar → paste → Go → bookmark or Add to Home Screen.")


if __name__ == "__main__":
    main()
