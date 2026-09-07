#!/usr/bin/env -S uv run --script
"""Discover CountryTabs URLs and import stub charts for a band catalog.

Typical workflow when adding new songs:
  1. Add songs to songs.yaml (update_bail_money_catalog.py can help)
  2. Stub .chopro files are created automatically or by catalog script
  3. Run this script to discover URLs and import charts:

     uv run scripts/import_charts.py BailMoneyBand --all

Options:
  --discover-only   Only update chart-sources.yaml
  --import-only     Skip discovery, import from existing chart-sources.yaml
  --batch-size N    Limit imports per run (default: 5; use --all for everything)
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("band_dir", type=Path, help="Band directory (e.g. BailMoneyBand)")
    parser.add_argument("--all", action="store_true", help="Import all stub charts with URLs")
    parser.add_argument("--batch-size", type=int, default=5, help="Max charts to import per run")
    parser.add_argument("--discover-only", action="store_true", help="Only discover URLs")
    parser.add_argument("--import-only", action="store_true", help="Skip URL discovery")
    parser.add_argument("--slug", action="append", help="Limit to specific slug(s)")
    parser.add_argument("--delay", type=float, default=1.0, help="Seconds between network requests")
    args = parser.parse_args()

    band_dir = args.band_dir
    if not band_dir.is_absolute():
        band_dir = ROOT / band_dir

    discover_script = ROOT / "scripts" / "discover_chart_sources.py"
    import_script = ROOT / "scripts" / "import_charts_batch.py"

    discover_cmd = ["uv", "run", str(discover_script), str(band_dir), "--delay", str(args.delay)]
    if args.slug:
        for slug in args.slug:
            discover_cmd.extend(["--slug", slug])

    import_cmd = ["uv", "run", str(import_script), str(band_dir), "--delay", str(args.delay)]
    if args.all:
        import_cmd.append("--all")
    else:
        import_cmd.extend(["--batch-size", str(args.batch_size)])
    if args.slug:
        for slug in args.slug:
            import_cmd.extend(["--slug", slug])

    if not args.import_only:
        print("=== Discovering CountryTabs URLs ===")
        subprocess.run(discover_cmd, check=True)

    if not args.discover_only:
        print("\n=== Importing charts ===")
        subprocess.run(import_cmd, check=True)


if __name__ == "__main__":
    main()
