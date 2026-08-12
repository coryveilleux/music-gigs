# Music Gigs

Song database and set list planner for band gigs. Each band/project has a directory with `band.yaml` (members) and `songs.yaml` (catalog). A FastAPI web app generates set lists with constraint-aware ordering and exports to CSV or plain text.

## Setup

Requires [uv](https://docs.astral.sh/uv/).

```bash
uv sync
```

## Run the web app

```bash
uv run uvicorn apps.web.main:app --reload
```

Open http://127.0.0.1:8000

## Band directory structure

```
TheOtters/
├── band.yaml    # band name and members
└── songs.yaml   # song catalog
```

### band.yaml

```yaml
name: The Otters
members:
  - id: alice
    name: Alice
  - id: bob
    name: Bob
```

### songs.yaml

```yaml
songs:
  - title: "Start Me Up"
    original_artist: "The Rolling Stones"
    key: "B"
    lead_singer: bob
    duration_seconds: 213
    active: true
    notes: |
      Optional arrangement notes.
```

Required fields: `title`, `original_artist`, `key`, `lead_singer`, `duration_seconds`, `active`.

Optional fields: `reference_artists`, `writers`, `structure`, `chords`, `lyrics`, `verse_hints`, `notes`.

## Import from Apple Music

Export a playlist from Apple Music (**File → Library → Export Playlist**), then run:

```bash
uv run scripts/import_apple_music.py ~/Documents/The\ Otters.txt TheOtters
```

The script also supports the older iTunes **Library XML** format (`Library.xml`) if you have that instead.

## Export catalog review list

Aligned, monospace-friendly list of all active songs for band review:

```bash
uv run scripts/export_catalog.py TheOtters -o catalog-review.txt
```

Format: `singer - key - title: original_artist` (sorted by singer, then title).

Also available from the web app as **Download catalog review list** on each band page.

## Set list rules

- Songs are auto-picked to roughly fill the gig duration
- Gigs ≤ 90 min → 1 set; longer gigs split into ~1-hour sets
- Ordering avoids: 3+ consecutive songs by same lead singer, back-to-back same artist, 3+ consecutive same key
