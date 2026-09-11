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

PDF export uses landscape letter, monospace Courier, and fits 10–15 songs per page
(4 pages for ~47 songs) so it's readable on top of an amp.

```bash
uv run scripts/export_catalog.py TheOtters -o TheOtters/catalog-review.pdf
```

Also available from the web app as **PDF for printing** on each band page.

## Gig HTML book (ChordPro charts)

For performance on phone or tablet, build a single offline HTML file from ChordPro charts and a set list:

```
BailMoneyBand/
├── band.yaml
├── songs.yaml          # catalog metadata (keys, notes)
├── charts/             # one .chopro file per song
│   └── i-never-lie.chopro
├── sets/
│   └── pilot-gig.yaml  # ordered sets for a gig
└── gigs/
    └── pilot-gig.html  # generated output
```

### Build

```bash
uv run scripts/build_gig_html.py BailMoneyBand sets/pilot-gig.yaml -o BailMoneyBand/gigs/pilot-gig.html
```

Features: numbered set list, search, transpose, Nashville numbers, **Structure** view (chords + lyric anchors per section), **Fit page** zoom, and **auto scroll** timed from song duration or `{tempo: N}` in the chart.

### Bulk chart import and restructure

Charts are imported from [CountryTabs](http://www.countrytabs.com/) into `.chopro` files. After import, many songs land as **one big section** — fine for reference, but not for adding gig notes section-by-section like Buy Me a Boat.

**1. Import** (first time or new songs in catalog):

```bash
uv run scripts/import_charts.py BailMoneyBand --all
```

**2. Restructure** — re-fetch from CountryTabs, split into intro/verse/chorus/bridge, add a `{comment: Structure: ...}` hint, and strip tab-staff junk. Skips charts you've finished (no “Imported from CountryTabs” line, or harmonies added):

```bash
# All songs on a gig setlist (skips Buy Me a Boat and other finished charts)
uv run scripts/restructure_charts.py BailMoneyBand \
  --set sets/lilac-hedge-farm-2026-09-12.yaml

# One song, overwrite even if already sectioned
uv run scripts/restructure_charts.py BailMoneyBand --slug folsom --force
```

Then open each chart and add your `{c: ...}` performance notes — chords and section breaks are already there.

**Already hand-edited charts** (Buy Me a Boat, I Never Lie, Gimme 3 Steps, etc.) are left alone. Songs with bad CountryTabs URLs are skipped with a warning (fix the URL in `chart-sources.yaml`).

**3. Rebuild the gig book** after chart changes:

```bash
uv run scripts/build_gig_html.py BailMoneyBand sets/lilac-hedge-farm-2026-09-12.yaml \
  -o BailMoneyBand/gigs/lilac-hedge-farm-2026-09-12.html
```

### Chart authoring (`.chopro`)

Charts are mostly standard [ChordPro](https://www.chordpro.org/). If bandmates import your `.chopro` files into **Songbook Pro**, **OnSong**, **Chordly**, etc., stick to the portable subset below — unknown directives are usually ignored or shown as raw text.

**Songbook Pro** (your singer): use bracket cues and standard `{c:}` / `{comment:}` — see [Songbook Pro ChordPro docs](https://songbook-pro.com/docs/manual/chordpro/). The gig book renders the same sources the same way.

#### Portable (standard ChordPro)

Safe to use in this gig book **and** other apps:

| Syntax | Purpose |
|--------|---------|
| `{title: ...}`, `{artist: ...}`, `{key: ...}`, `{tempo: ...}` | Song metadata |
| `{start_of_verse}`, `{end_of_verse}`, `{start_of_chorus}`, … | Sections (also `{soc}`, `{eoc}`, etc. in some apps) |
| `{start_of_verse: label}` | Section with optional label |
| `[Am]` `[G/B]` | Chords inline with lyrics |
| `[STOP]` `[Dm7 (play twice)]` | Songbook Pro inline cues in the chord row (text in brackets) |
| `{ti: (STOP)}` `{text_italic: hold}` | Mid-line italic callout in the lyric row (ChordPro 5/6) |
| `{comment: ...}` or `{c: ...}` | Visible instruction (on its own line) |
| `# line at column 1` | Hidden comment (not rendered) |

**Tip for directions in other apps:** use `{c: ...}` or `{comment: ...}` on its own line between lyric lines. Most renderers show it as a grey instruction block. Our gig book styles it as an orange inline callout instead, but the source text is the same.

**Section numbering** in the gig book is automatic (Verse 1 / Verse 2 only when there are 2+ of that type). You do **not** need `{c: Verse 2}` for numbering — other apps may still want `{c: Verse 2}` as a manual header if they don’t auto-number.

#### Gig-book only (custom extensions)

These work in **this project’s HTML gig book** only. Other software will not understand them (may show `{harmony: ...}` literally or skip it):

| Syntax | Purpose |
|--------|---------|
| `{dir: ...}`, `{direction: ...}`, `{note: ...}` | Same idea as `{c:}` — use `{c:}` if you need portability |
| `{harmony: ...}`, `{harm: ...}`, `{bv: ...}` | Whole backing-vocal line |
| `<<words>>` | Inline harmony highlight on specific words |
| `\|C\| \|F\| \|G\|` | Bar notation for instrumental changes |
| Chord-only lines (`[C]  [F]  [G]` with no lyrics) | Instrumental changes (portable as plain `[chord]` lines; spacing/extra features are ours) |

**If only you use the gig book:** feel free to use the custom tags for harmonies and tighter inline layout.

**If others import your charts:** prefer `{c: ...}` for directions; for harmonies, either keep `{harmony: ...}` / `<<...>>` (they’ll see the text) or duplicate notes in a `{comment: ...}` line they can read in any app.

#### Examples

**Mid-line cues** — pick the style that matches who needs to read the chart:

**Songbook Pro brackets** (cue in the chord row above the word):

```chordpro
Well, maybe [D]so, but it could [STOP] buy me a [A]boat
My [Dm7 (play twice)]lyric line continues here
```

`[STOP]` is plain text in brackets — Songbook Pro shows it above the lyric without breaking the line. `[Dm7 (play twice)]` stacks a chord and annotation at one spot. The `[*STOP]` / `[G*HOLD]` asterisk form still works if another app might misread bare `[STOP]` as a chord.

**ChordPro inline italic** (callout inside the lyric line):

```chordpro
Well, maybe [D]so, but it could {ti: (STOP)} buy me a [A]boat
{text_italic: hold} on the downbeat
```

`{ti: ...}` and `{text_italic: ...}` are equivalent here. `{tb: ...}` / `{text_bold: ...}` render bold if you need emphasis instead of italic.

**Own-line directions** (portable `{c:}`; `{dir:}` is an alias in the gig book only):

```chordpro
{start_of_verse}
Well it's been some [Bm]time
{c: go quiet — drums stop time here}
Still look like an [D]angel
{end_of_verse}
```

**Harmonies** (gig-book extensions):

```chordpro
Lead sings here and <<you sing harmony here>> on these words
{harmony: optional full line of backing vocal lyrics}
```

Portable alternative for other apps:

```chordpro
{c: BV: you sing harmony on "these words"}
Lead sings here and these words
```

**Instrumental / intro changes:**

```chordpro
{start_of_intro: pickup}
|F#m| |D| |A| |E|
{c: Vocal enters on beat 2 of bar 2}
[F#m]     [D]        [A]           [E]
{end_of_intro}
```

Bar notation and chord-only lines are gig-book conventions; in other apps, `{c: F#m - D - A - E}` or a chord line `[F#m] [D] [A] [E]` still reads fine.

#### Song structure and chord progressions (portable hints)

Structure view **auto-detects** repeating progressions from the chords in each section (e.g. Buy Me a Boat chorus → `D · G · D · A  (×2)`). When detection isn’t enough, add portable `{comment: ...}` hints at the top of the chart:

```chordpro
{comment: Structure: I V C V C B C}
{comment: Progression verse: D G D A x2}
{comment: Progression chorus: D G D A x2}
```

Or per-section override (shows as a `{c: ...}` line in other apps):

```chordpro
{start_of_chorus}
{c: progression: D G D A x2}
...
```

Formats accepted: `D G D A x2`, `D-G-D-A ×2`, `D | G | D | A (x2)`.

`build_gig_html.py` prints a **warning** when `{comment: Structure: ...}` is missing (still builds with best-guess detection).

**Structure view** uses detected or hinted progressions, plus lyric anchors and section notes. Full chart view uses the same `.chopro` source.

### Open on iPhone

iOS won't run JavaScript when you tap an `.html` file in **Files** (Quick Look only). You need one of the workflows below for transpose, search, Structure view, and auto scroll.

Share the `.html` in a **shared iCloud folder** before the gig so everyone has a local copy. Set up your chosen method at home on Wi‑Fi — all of these work **offline at the venue** once configured.

#### Option A: data URI → Safari (Mac + Universal Clipboard)

Best if you build on a Mac and want native Safari (bookmark / Home Screen).

```bash
# 1. Build the gig book
uv run scripts/build_gig_html.py BailMoneyBand sets/lilac-hedge-farm-2026-09-12.yaml \
  -o BailMoneyBand/gigs/lilac-hedge-farm-2026-09-12.html

# 2. Copy data URI to clipboard (macOS)
uv run scripts/gig_html_to_safari.py BailMoneyBand/gigs/lilac-hedge-farm-2026-09-12.html
```

On your iPhone (same Apple ID, Bluetooth/Wi‑Fi on for Handoff):

1. Open **Safari**
2. Tap the **address bar** → **Paste** → **Go**
3. Wait a few seconds for a large gig book to load
4. **Share → Add to Bookmark** or **Add to Home Screen** for gig night

Manual equivalent (no script):

```bash
base64 -i BailMoneyBand/gigs/pilot-gig.html | (echo -n "data:text/html;base64,"; cat) | pbcopy
```

The script adds `charset=utf-8` and prints the URI size. Large set lists (~30+ songs) produce ~1 MB URIs — Safari handles them, but loading can take a moment.

To save the URI without copying:

```bash
uv run scripts/gig_html_to_safari.py BailMoneyBand/gigs/pilot-gig.html -o pilot-gig.uri.txt --print
```

#### Option B: Code viewer app (easiest for bandmates)

**Most reliable way to open a local `.html` file with full JavaScript, no Mac required.** Free apps from the App Store act as an offline web viewer:

- [Koder Code Editor](https://apps.apple.com/app/koder-code-editor/id1005121427)
- [Textastic](https://apps.apple.com/app/textastic-code-editor/id1049254268)
- [Documents by Readdle](https://apps.apple.com/app/documents-by-readdle/id364901807) (free; many band members may already have it)

Setup (once per gig book):

1. Install the app
2. **Import** the `.html` from Files or your shared iCloud folder
3. Open the file and tap **Preview** (play/eye icon)
4. Optional: add the app or a saved file shortcut to your Home Screen

Transpose, search, Structure view, and auto scroll all work offline.

#### Option C: Shortcuts → Safari (no third-party apps)

Uses Apple's built-in **Shortcuts** app to hand the file to Safari:

1. Open **Shortcuts** → **+** (new shortcut)
2. Add action **Get File** → tap **File** and pick your gig `.html` from Files/iCloud
3. Add action **Open in** (or **Open File in…**) → choose **Safari**
4. Run the shortcut (▶) to test — Safari should open with JavaScript enabled
5. **Share** on the shortcut → **Add to Home Screen** for one-tap launch at the gig

Shortcut behavior can vary by iOS version. If Safari opens a blank page, use Option B or A instead.

#### Option D: Files → Quick Look (static fallback)

Tap the `.html` in **Files** — no setup, works offline, but **no JavaScript**. You still get the full set list and all charts (scroll to read). Good backup if nothing else is configured.

#### Comparison

| Method | Full JS | Needs Mac | Third-party app | Best for |
|--------|---------|-----------|-----------------|----------|
| **A. data URI → Safari** | Yes | Yes (to copy URI) | No | Bookmark in Safari, Add to Home Screen |
| **B. Code viewer app** | Yes | No | Yes (free) | Bandmates with only the shared `.html` file |
| **C. Shortcuts → Safari** | Yes* | No | No | No extra apps if Shortcut works on your phone |
| **D. Quick Look** | No | No | No | Emergency fallback |

\*Option C depends on iOS version; Option B is the most dependable for local files.

## Set list rules

- Songs are auto-picked to roughly fill the gig duration
- Gigs ≤ 90 min → 1 set; longer gigs split into ~1-hour sets
- Ordering avoids: 3+ consecutive songs by same lead singer, back-to-back same artist, 3+ consecutive same key
