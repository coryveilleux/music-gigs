from __future__ import annotations

import base64
import html
import json
from pathlib import Path

import yaml

from music_gigs.chordpro import (
    chordpro_to_structured,
    chart_structure_warnings,
    parse_chordpro,
    progression_hints_from_metadata,
    render_chordpro_html,
    section_outline_from_structured,
)
from music_gigs.loader import load_band_config
from music_gigs.slug import slugify


def load_set_file(set_path: Path) -> dict:
    with set_path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_chart(band_dir: Path, slug: str) -> str:
    chart_path = band_dir / "charts" / f"{slug}.chopro"
    if not chart_path.exists():
        raise FileNotFoundError(f"Missing chart: {chart_path}")
    return chart_path.read_text(encoding="utf-8")


def _parse_positive_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    text = str(value).strip()
    if not text.isdigit():
        return None
    parsed = int(text)
    return parsed if parsed > 0 else None


def _parse_positive_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        parsed = float(str(value).strip())
    except ValueError:
        return None
    return parsed if parsed > 0 else None


def _resolve_scroll_fields(
    parsed_metadata: dict[str, str],
    catalog_meta: dict,
) -> tuple[int | None, float | None]:
    """Return (scroll_duration_seconds, scroll_multiplier) for auto-scroll timing."""
    scroll_duration = _parse_positive_int(catalog_meta.get("scroll_duration_seconds"))
    chart_scroll = _parse_positive_int(parsed_metadata.get("scroll_duration"))
    if chart_scroll is not None:
        scroll_duration = chart_scroll

    scroll_multiplier = _parse_positive_float(catalog_meta.get("scroll_multiplier"))
    chart_multiplier = _parse_positive_float(parsed_metadata.get("scroll_multiplier"))
    if chart_multiplier is not None:
        scroll_multiplier = chart_multiplier

    return scroll_duration, scroll_multiplier


def catalog_by_slug(band_dir: Path) -> dict[str, dict]:
    songs_file = band_dir / "songs.yaml"
    if not songs_file.exists():
        return {}
    with songs_file.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    result: dict[str, dict] = {}
    for song in data.get("songs", []):
        title = song.get("title") or ""
        slug = slugify(title)
        result[slug] = {
            "title": title,
            "key": song.get("key") or "",
            "original_artist": song.get("original_artist") or "",
            "notes": song.get("notes") or "",
            "duration_seconds": song.get("duration_seconds"),
            "scroll_duration_seconds": song.get("scroll_duration_seconds"),
            "scroll_multiplier": song.get("scroll_multiplier"),
        }
    return result


def build_gig_data(band_dir: Path, set_path: Path) -> dict:
    band_config = load_band_config(band_dir)
    set_data = load_set_file(set_path)
    catalog = catalog_by_slug(band_dir)

    sets_out = []
    all_songs = []
    song_index = 0

    for set_info in set_data.get("sets", []):
        set_number = set_info["number"]
        set_songs = []
        for entry in set_info.get("songs", []):
            slug = entry["slug"]
            chart_text = load_chart(band_dir, slug)
            parsed = parse_chordpro(chart_text)
            meta = catalog.get(slug, {})
            title = parsed.metadata.get("title") or meta.get("title") or slug
            key = parsed.metadata.get("key") or meta.get("key") or ""
            artist = parsed.metadata.get("artist") or meta.get("original_artist") or ""
            tempo_raw = parsed.metadata.get("tempo", "")
            tempo = int(tempo_raw) if str(tempo_raw).isdigit() else None
            duration = meta.get("duration_seconds")
            if not duration:
                duration_raw = parsed.metadata.get("duration", "")
                duration = int(duration_raw) if str(duration_raw).isdigit() else None
            scroll_duration, scroll_multiplier = _resolve_scroll_fields(
                parsed.metadata, meta
            )
            structured = chordpro_to_structured(parsed)
            progression_hints = progression_hints_from_metadata(parsed.metadata)

            song_index += 1
            song_obj = {
                "slug": slug,
                "title": title,
                "artist": artist,
                "key": key,
                "set": set_number,
                "number": song_index,
                "tempo": tempo,
                "duration_seconds": duration,
                "scroll_duration_seconds": scroll_duration,
                "scroll_multiplier": scroll_multiplier,
                "structure": parsed.metadata.get("structure", ""),
                "sections": structured,
                "outline": section_outline_from_structured(structured, progression_hints),
                "chart_warnings": chart_structure_warnings(parsed),
                "body_html": render_chordpro_html(parsed),
            }
            set_songs.append(song_obj)
            all_songs.append(song_obj)

        sets_out.append({"number": set_number, "songs": set_songs})

    return {
        "band": band_config.name,
        "gig": set_data.get("name", "Gig"),
        "date": str(set_data.get("date") or ""),
        "venue": set_data.get("venue", ""),
        "sets": sets_out,
        "songs": all_songs,
    }


def _gig_meta_text(gig_data: dict) -> str:
    return " · ".join(
        part for part in [gig_data.get("gig"), gig_data.get("date"), gig_data.get("venue")] if part
    )


def _static_song_list_html(gig_data: dict) -> str:
    parts: list[str] = []
    for set_info in gig_data["sets"]:
        parts.append(
            f'<div class="set-header" id="set-{set_info["number"]}">Set {set_info["number"]}</div>'
        )
        for song in set_info["songs"]:
            key_part = (
                f'<span class="key">{html.escape(song["key"])}</span>' if song.get("key") else ""
            )
            parts.append(
                f'<a class="song-link" href="#song-{html.escape(song["slug"])}">'
                f'<span class="num">{song["number"]}.</span>{html.escape(song["title"])}'
                f"{key_part}</a>"
            )
    return "\n".join(parts)


def _static_charts_html(gig_data: dict) -> str:
    parts: list[str] = []
    for song in gig_data["songs"]:
        artist_part = f' · {html.escape(song["artist"])}' if song.get("artist") else ""
        parts.append(
            f'<article class="static-song" id="song-{html.escape(song["slug"])}">'
            f'<div class="song-header">'
            f'<h1>{song["number"]}. {html.escape(song["title"])}</h1>'
            f'<p class="artist">Set {song["set"]}{artist_part}</p>'
            f"</div>"
            f'{song.get("body_html", "")}'
            f"</article>"
        )
    return "\n".join(parts)


def _gig_payload_for_js(gig_data: dict) -> dict:
    def strip_song(song: dict) -> dict:
        return {key: value for key, value in song.items() if key != "body_html"}

    return {
        "band": gig_data["band"],
        "gig": gig_data["gig"],
        "date": gig_data["date"],
        "venue": gig_data["venue"],
        "sets": [
            {"number": set_info["number"], "songs": [strip_song(song) for song in set_info["songs"]]}
            for set_info in gig_data["sets"]
        ],
        "songs": [strip_song(song) for song in gig_data["songs"]],
    }


def html_to_data_uri(html_bytes: bytes) -> str:
    """Encode HTML for opening in Safari via a data: URI (e.g. Universal Clipboard)."""
    encoded = base64.b64encode(html_bytes).decode("ascii")
    return f"data:text/html;charset=utf-8;base64,{encoded}"


def render_gig_html(gig_data: dict) -> str:
    payload = json.dumps(_gig_payload_for_js(gig_data), ensure_ascii=False)
    payload = payload.replace("</", "<\\/")
    band_name = html.escape(gig_data["band"])
    gig_meta = html.escape(_gig_meta_text(gig_data))
    static_list = _static_song_list_html(gig_data)
    static_charts = _static_charts_html(gig_data)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <meta name="apple-mobile-web-app-capable" content="yes">
  <meta name="theme-color" content="#111111">
  <title>{gig_data["band"]} — {gig_data["gig"]}</title>
  <style>
    :root {{
      --bg: #111;
      --surface: #1a1a1a;
      --surface-raised: #252525;
      --text: #f2f2f2;
      --muted: #aaa;
      --note-text: #ccc;
      --accent: #f5c542;
      --on-accent: #111;
      --border: #333;
      --nav-bg: rgba(17, 17, 17, 0.95);
      --hover-bg: #252525;
      --direction: #f5a742;
      --harmony: #9fd4ff;
      --harmony-underline: #5aa8e8;
      --code-bg: #0a0a0a;
      --code-text: #ddd;
      --scroll-active: #3d7a3d;
      --scroll-active-text: #fff;
      --tap: 48px;
    }}
    * {{ box-sizing: border-box; }}
    html, body {{ margin: 0; padding: 0; background: var(--bg); color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, sans-serif; }}
    .hidden {{ display: none !important; }}
    .nav-bar {{
      position: fixed; left: 0; right: 0; z-index: 100;
      display: flex; gap: 0.5rem; padding: 0.5rem;
      background: var(--nav-bg); border-bottom: 1px solid var(--border);
      backdrop-filter: blur(8px);
    }}
    .nav-top {{ top: 0; }}
    .nav-bottom {{ bottom: 0; border-bottom: none; border-top: 1px solid var(--border); }}
    .nav-bar button, .nav-bar a.btn {{
      flex: 1; min-height: var(--tap); border: 1px solid var(--border);
      background: var(--surface); color: var(--text); border-radius: 8px;
      font-size: 0.95rem; text-decoration: none; display: flex;
      align-items: center; justify-content: center; cursor: pointer;
    }}
    .nav-bar button.primary {{ background: var(--accent); color: var(--on-accent); border-color: var(--accent); font-weight: 600; }}
    main {{ padding: 4.5rem 1rem 5.5rem; max-width: 900px; margin: 0 auto; }}
    h1 {{ font-size: 1.5rem; margin: 0 0 0.25rem; }}
    .meta {{ color: var(--muted); margin-bottom: 1rem; font-size: 0.95rem; }}
    .search-wrap {{ position: relative; margin-bottom: 1rem; }}
    .search {{
      width: 100%; padding: 0.75rem 1rem; font-size: 1.1rem;
      border-radius: 10px; border: 1px solid var(--border);
      background: var(--surface); color: var(--text);
    }}
    .search-suggestions {{
      position: absolute; left: 0; right: 0; top: calc(100% + 4px);
      background: var(--surface); border: 1px solid var(--border);
      border-radius: 10px; max-height: 50vh; overflow-y: auto;
      z-index: 50; box-shadow: 0 8px 24px rgba(0,0,0,0.4);
    }}
    .search-suggestions:empty {{ display: none; }}
    .suggestion {{
      display: block; width: 100%; text-align: left;
      padding: 0.75rem 1rem; border: none; border-bottom: 1px solid var(--border);
      background: transparent; color: var(--text); font-size: 1rem;
      cursor: pointer;
    }}
    .suggestion:last-child {{ border-bottom: none; }}
    .suggestion:active, .suggestion:hover {{ background: var(--hover-bg); }}
    .theme-bar {{
      display: flex; flex-wrap: wrap; gap: 0.75rem; align-items: center;
      margin-bottom: 1rem; padding: 0.75rem;
      background: var(--surface); border: 1px solid var(--border); border-radius: 10px;
    }}
    .theme-bar label {{
      display: flex; flex-direction: column; gap: 0.25rem;
      font-size: 0.8rem; color: var(--muted); flex: 1 1 8rem;
    }}
    .theme-bar select {{
      min-height: 2.5rem; padding: 0.35rem 0.5rem; border-radius: 8px;
      border: 1px solid var(--border); background: var(--surface-raised);
      color: var(--text); font-size: 0.95rem;
    }}
    .suggestion .meta {{ color: var(--muted); font-size: 0.85rem; margin-left: 0.5rem; }}
    .set-header {{
      color: var(--accent); font-weight: 700; font-size: 1.1rem;
      margin: 1.25rem 0 0.5rem; padding-top: 0.5rem;
      border-top: 1px solid var(--border);
    }}
    .set-header:first-of-type {{ border-top: none; }}
    .song-link {{
      display: block; padding: 0.85rem 1rem; margin-bottom: 0.4rem;
      background: var(--surface); border: 1px solid var(--border);
      border-radius: 10px; color: var(--text); text-decoration: none;
      font-size: 1.05rem;
    }}
    .song-link .num {{ color: var(--accent); font-weight: 700; margin-right: 0.5rem; }}
    .song-link .key {{ color: var(--muted); font-size: 0.9rem; margin-left: 0.5rem; }}
    .song-header h1 {{ font-size: 1.6rem; }}
    .song-header .artist {{ color: var(--muted); margin-bottom: 0.75rem; }}
    .transpose-bar {{
      display: flex; flex-wrap: wrap; align-items: center; gap: 0.5rem;
      margin-bottom: 1.25rem; padding: 0.75rem;
      background: var(--surface); border: 1px solid var(--border); border-radius: 10px;
    }}
    .transpose-bar .key-label {{ font-weight: 600; margin-right: 0.25rem; }}
    .transpose-bar button {{
      min-width: 2.5rem; min-height: 2.5rem; padding: 0.35rem 0.6rem;
      border: 1px solid var(--border); border-radius: 8px;
      background: var(--surface-raised); color: var(--text); font-size: 1rem; cursor: pointer;
    }}
    .transpose-bar button.reset {{ font-size: 0.85rem; min-width: auto; }}
    .transpose-bar label.nashville {{
      display: flex; align-items: center; gap: 0.35rem;
      margin-left: auto; font-size: 0.9rem; color: var(--muted);
    }}
    .section-label {{
      color: var(--accent); font-size: 0.95rem; text-transform: uppercase;
      letter-spacing: 0.04em; margin: 0 0 0.65rem;
    }}
    .chart-section {{
      margin-bottom: 2.25rem;
    }}
    .chart-section + .chart-section {{
      padding-top: 1.1rem;
      border-top: 1px solid var(--border);
    }}
    .lyric-row {{
      font-family: "Courier New", Courier, monospace;
      font-size: 1.1rem; margin-bottom: 1rem;
    }}
    .lyric-row .chords {{
      color: var(--accent); font-weight: 700;
      min-height: 1.35em; white-space: pre; overflow-x: auto;
    }}
    .chord-track {{
      position: relative;
      font-family: "Courier New", Courier, monospace;
      font-size: 1.1rem;
      min-height: 2.4em;
      margin-bottom: 0.1rem;
      overflow-x: auto;
    }}
    .chord-track .chord-marker {{
      position: absolute;
      top: 0;
      display: flex;
      flex-direction: column;
      align-items: flex-start;
      white-space: nowrap;
    }}
    .chord-track .chord {{
      color: var(--accent);
      font-weight: 700;
    }}
    .chord-track .chord-cue {{
      color: var(--direction);
      font-style: italic;
      font-weight: 600;
      font-size: 0.9em;
      display: block;
    }}
    .chord-track .nashville {{
      color: var(--muted);
      font-size: 0.85em;
      font-weight: 500;
      display: block;
      text-align: center;
    }}
    .lyric-row .lyrics {{
      color: var(--text); white-space: pre-wrap; line-height: 1.5;
    }}
    .lyric-row.lyrics-only .lyrics {{ margin-top: 0; }}
    .note, .note-block .note {{
      color: var(--note-text); font-style: italic; font-size: 1.15rem; line-height: 1.45;
      margin: 0.5rem 0;
    }}
    .inline-direction {{
      color: var(--direction); font-style: italic; font-size: 1.15rem; line-height: 1.45;
      margin: 0.35rem 0 0.15rem; padding-left: 0.5rem;
      border-left: 3px solid var(--direction);
    }}
    .lyrics .inline-direction {{
      display: inline;
      margin: 0;
      padding: 0;
      border: 0;
      font-size: inherit;
      font-weight: 600;
    }}
    .harmony, .harmony-line {{
      color: var(--harmony); font-weight: 600;
      text-decoration: underline; text-decoration-color: var(--harmony-underline);
      text-underline-offset: 0.15em;
    }}
    .harmony-line {{ margin: 0.35rem 0; font-style: italic; }}
    .bars, .chord-line {{
      font-family: "Courier New", Courier, monospace;
      color: var(--accent); font-weight: 700; margin: 0.35rem 0;
    }}
    pre.tab, pre.abc {{
      background: var(--code-bg); border: 1px solid var(--border);
      border-radius: 8px; padding: 0.75rem; overflow-x: auto;
      font-family: "Courier New", Courier, monospace;
      font-size: 0.95rem; line-height: 1.35; color: var(--code-text);
    }}
    pre.abc {{ border-color: var(--border); }}
    .performance-bar {{
      display: flex; flex-wrap: wrap; gap: 0.5rem;
      margin-bottom: 1rem; padding: 0.75rem;
      background: var(--surface); border: 1px solid var(--border); border-radius: 10px;
    }}
    .perf-group {{
      display: flex; gap: 0.35rem; flex: 1 1 auto; min-width: 0;
    }}
    .perf-btn {{
      flex: 1; min-height: var(--tap); padding: 0.5rem 0.65rem;
      border: 1px solid var(--border); border-radius: 8px;
      background: var(--surface-raised); color: var(--text); font-size: 0.9rem; cursor: pointer;
    }}
    .perf-btn.active {{
      background: var(--accent); color: var(--on-accent); border-color: var(--accent); font-weight: 600;
    }}
    .perf-btn.scroll-btn.active {{
      background: var(--scroll-active); color: var(--scroll-active-text);
      border-color: var(--scroll-active);
    }}
    .scroll-hint {{
      width: 100%; font-size: 0.8rem; color: var(--muted); margin-top: 0.15rem;
    }}
    .chart-body {{ margin-top: 0.25rem; }}
    .outline-section {{
      margin-bottom: 1rem; padding: 0.85rem 1rem;
      background: var(--surface); border: 1px solid var(--border); border-radius: 10px;
    }}
    .outline-section .section-label {{ margin-top: 0; }}
    .outline-chords {{
      font-family: "Courier New", Courier, monospace;
      color: var(--accent); font-weight: 700; font-size: 1.05rem;
      margin: 0.35rem 0 0.5rem;
    }}
    .outline-chord-compact {{
      font-family: "Courier New", Courier, monospace;
      color: var(--accent); font-weight: 700; font-size: 1.05rem;
      margin: 0.15rem 0; line-height: 1.5;
    }}
    .outline-chord-compact .repeat {{
      color: var(--muted); font-weight: 500; font-size: 0.9em;
    }}
    .outline-hint {{
      font-size: 0.95rem; line-height: 1.45; margin: 0.35rem 0;
      color: var(--text);
    }}
    .outline-hint .hint-label {{
      color: var(--muted); font-size: 0.8rem; text-transform: uppercase;
      letter-spacing: 0.04em; margin-right: 0.35rem;
    }}
    #static-charts {{ margin-top: 2rem; }}
    #static-charts .static-song {{
      padding: 2rem 0;
      border-top: 1px solid var(--border);
    }}
    #static-charts .static-song:first-child {{ border-top: none; }}
    html.js #static-charts {{ display: none; }}
  </style>
</head>
<body>
  <div id="nav-top" class="nav-bar nav-top hidden">
    <button type="button" id="btn-prev">◀ Prev</button>
    <button type="button" id="btn-setlist" class="primary">Set list</button>
    <button type="button" id="btn-next">Next ▶</button>
  </div>

  <main id="app">
    <div id="list-view">
      <h1 id="band-name">{band_name}</h1>
      <p class="meta" id="gig-meta">{gig_meta}</p>
      <div class="search-wrap">
        <input class="search" id="search" type="search" placeholder="Search songs..." autocomplete="off" enterkeyhint="search">
        <div class="search-suggestions" id="search-suggestions"></div>
      </div>
      <div class="theme-bar" aria-label="Chart colors">
        <label>
          Look
          <select id="theme-mode">
            <option value="dark">Night (indoor)</option>
            <option value="light">Day (outdoor)</option>
          </select>
        </label>
        <label>
          Palette
          <select id="theme-palette"></select>
        </label>
      </div>
      <div id="song-list">{static_list}</div>
    </div>
    <div id="song-view" class="hidden"></div>
  </main>

  <section id="static-charts" aria-label="Charts">
    {static_charts}
  </section>

  <div id="nav-bottom" class="nav-bar nav-bottom hidden">
    <button type="button" id="btn-scroll">▶ Scroll</button>
    <button type="button" id="btn-jump-set">This set</button>
    <button type="button" id="btn-next-bottom">Next ▶</button>
  </div>

  <script>
    document.documentElement.classList.add("js");
    const GIG = {payload};

    const THEME_STORAGE_KEY = "music-gigs-chart-theme";
    const THEME_PALETTES = {{
      dark: {{
        stage: {{
          "--bg": "#111111",
          "--surface": "#1a1a1a",
          "--surface-raised": "#252525",
          "--text": "#f2f2f2",
          "--muted": "#aaaaaa",
          "--note-text": "#cccccc",
          "--accent": "#f5c542",
          "--on-accent": "#111111",
          "--border": "#333333",
          "--nav-bg": "rgba(17, 17, 17, 0.95)",
          "--hover-bg": "#252525",
          "--direction": "#f5a742",
          "--harmony": "#9fd4ff",
          "--harmony-underline": "#5aa8e8",
          "--code-bg": "#0a0a0a",
          "--code-text": "#dddddd",
          "--scroll-active": "#3d7a3d",
          "--scroll-active-text": "#ffffff",
        }},
        warm: {{
          "--bg": "#14110e",
          "--surface": "#1f1a15",
          "--surface-raised": "#2a221b",
          "--text": "#f6efe6",
          "--muted": "#b8a998",
          "--note-text": "#d4c8b8",
          "--accent": "#ffb84d",
          "--on-accent": "#1a1208",
          "--border": "#3d3228",
          "--nav-bg": "rgba(20, 17, 14, 0.96)",
          "--hover-bg": "#2a221b",
          "--direction": "#ff9f43",
          "--harmony": "#ffc971",
          "--harmony-underline": "#e08b2d",
          "--code-bg": "#0f0c09",
          "--code-text": "#e8dfd3",
          "--scroll-active": "#4d7c3a",
          "--scroll-active-text": "#ffffff",
        }},
        contrast: {{
          "--bg": "#000000",
          "--surface": "#121212",
          "--surface-raised": "#1e1e1e",
          "--text": "#ffffff",
          "--muted": "#c8c8c8",
          "--note-text": "#e0e0e0",
          "--accent": "#ffe566",
          "--on-accent": "#000000",
          "--border": "#444444",
          "--nav-bg": "rgba(0, 0, 0, 0.96)",
          "--hover-bg": "#1e1e1e",
          "--direction": "#ffd24d",
          "--harmony": "#b8e6ff",
          "--harmony-underline": "#6ec8ff",
          "--code-bg": "#050505",
          "--code-text": "#f0f0f0",
          "--scroll-active": "#2f9e44",
          "--scroll-active-text": "#ffffff",
        }},
      }},
      light: {{
        sun: {{
          "--bg": "#f8f4e8",
          "--surface": "#fffdf6",
          "--surface-raised": "#f0ead8",
          "--text": "#1f1a12",
          "--muted": "#5c5345",
          "--note-text": "#4a4338",
          "--accent": "#b45309",
          "--on-accent": "#fffaf0",
          "--border": "#d4c9b0",
          "--nav-bg": "rgba(248, 244, 232, 0.96)",
          "--hover-bg": "#efe6d0",
          "--direction": "#c2410c",
          "--harmony": "#1d4ed8",
          "--harmony-underline": "#3b82f6",
          "--code-bg": "#f3ede0",
          "--code-text": "#292524",
          "--scroll-active": "#15803d",
          "--scroll-active-text": "#ffffff",
        }},
        cloud: {{
          "--bg": "#f2f4f8",
          "--surface": "#ffffff",
          "--surface-raised": "#e8ecf2",
          "--text": "#111827",
          "--muted": "#4b5563",
          "--note-text": "#374151",
          "--accent": "#1d4ed8",
          "--on-accent": "#ffffff",
          "--border": "#cbd5e1",
          "--nav-bg": "rgba(242, 244, 248, 0.96)",
          "--hover-bg": "#e5eaf0",
          "--direction": "#b45309",
          "--harmony": "#7c3aed",
          "--harmony-underline": "#8b5cf6",
          "--code-bg": "#e8ecf2",
          "--code-text": "#1f2937",
          "--scroll-active": "#047857",
          "--scroll-active-text": "#ffffff",
        }},
        outdoor: {{
          "--bg": "#ffffff",
          "--surface": "#fafafa",
          "--surface-raised": "#eeeeee",
          "--text": "#000000",
          "--muted": "#333333",
          "--note-text": "#1a1a1a",
          "--accent": "#000000",
          "--on-accent": "#ffffff",
          "--border": "#999999",
          "--nav-bg": "rgba(255, 255, 255, 0.97)",
          "--hover-bg": "#e8e8e8",
          "--direction": "#9a3412",
          "--harmony": "#1e40af",
          "--harmony-underline": "#1d4ed8",
          "--code-bg": "#f3f3f3",
          "--code-text": "#111111",
          "--scroll-active": "#166534",
          "--scroll-active-text": "#ffffff",
        }},
      }},
    }};
    const PALETTE_LABELS = {{
      dark: {{ stage: "Stage", warm: "Warm", contrast: "High contrast" }},
      light: {{ sun: "Sun", cloud: "Cloud", outdoor: "Outdoor bold" }},
    }};
    const DEFAULT_THEME = {{ mode: "dark", palette: "stage" }};

    function applyTheme(mode, palette) {{
      const vars = THEME_PALETTES[mode] && THEME_PALETTES[mode][palette];
      if (!vars) return;
      const root = document.documentElement;
      for (const [name, value] of Object.entries(vars)) {{
        root.style.setProperty(name, value);
      }}
      root.dataset.themeMode = mode;
      root.dataset.themePalette = palette;
      const meta = document.querySelector('meta[name="theme-color"]');
      if (meta) meta.setAttribute("content", vars["--bg"]);
    }}

    function parseStoredTheme() {{
      try {{
        const raw = localStorage.getItem(THEME_STORAGE_KEY);
        if (!raw) return {{ ...DEFAULT_THEME }};
        const [mode, palette] = raw.split(":");
        if (THEME_PALETTES[mode] && THEME_PALETTES[mode][palette]) {{
          return {{ mode, palette }};
        }}
      }} catch (e) {{}}
      return {{ ...DEFAULT_THEME }};
    }}

    function storeTheme(mode, palette) {{
      try {{
        localStorage.setItem(THEME_STORAGE_KEY, `${{mode}}:${{palette}}`);
      }} catch (e) {{}}
    }}

    function populatePaletteSelect(mode, selected) {{
      const select = document.getElementById("theme-palette");
      if (!select) return;
      const labels = PALETTE_LABELS[mode] || {{}};
      select.innerHTML = "";
      for (const id of Object.keys(THEME_PALETTES[mode] || {{}})) {{
        const option = document.createElement("option");
        option.value = id;
        option.textContent = labels[id] || id;
        select.appendChild(option);
      }}
      if (selected && THEME_PALETTES[mode][selected]) {{
        select.value = selected;
      }}
    }}

    function initThemeControls() {{
      const modeSelect = document.getElementById("theme-mode");
      const paletteSelect = document.getElementById("theme-palette");
      if (!modeSelect || !paletteSelect) return;
      let theme = parseStoredTheme();
      modeSelect.value = theme.mode;
      populatePaletteSelect(theme.mode, theme.palette);
      applyTheme(theme.mode, theme.palette);

      modeSelect.addEventListener("change", () => {{
        const mode = modeSelect.value;
        const firstPalette = Object.keys(THEME_PALETTES[mode] || {{}})[0];
        populatePaletteSelect(mode, firstPalette);
        theme = {{ mode, palette: paletteSelect.value }};
        applyTheme(theme.mode, theme.palette);
        storeTheme(theme.mode, theme.palette);
      }});
      paletteSelect.addEventListener("change", () => {{
        theme = {{ mode: modeSelect.value, palette: paletteSelect.value }};
        applyTheme(theme.mode, theme.palette);
        storeTheme(theme.mode, theme.palette);
      }});
    }}

    initThemeControls();

    const navTop = document.getElementById("nav-top");
    const navBottom = document.getElementById("nav-bottom");
    const listView = document.getElementById("list-view");
    const songView = document.getElementById("song-view");
    const songList = document.getElementById("song-list");
    const searchInput = document.getElementById("search");
    const suggestions = document.getElementById("search-suggestions");
    const bandName = document.getElementById("band-name");
    const gigMeta = document.getElementById("gig-meta");

    bandName.textContent = GIG.band;
    gigMeta.textContent = [GIG.gig, GIG.date, GIG.venue].filter(Boolean).join(" · ");

    const CHROMATIC = ["C","C#","D","D#","E","F","F#","G","G#","A","A#","B"];
    const FLAT_TO_SHARP = {{Db:"C#",Eb:"D#",Gb:"F#",Ab:"G#",Bb:"A#",Cb:"B",Fb:"E"}};
    const MAJOR_SCALE = [0,2,4,5,7,9,11];

    const transposeOffsets = {{}};
    let showNashville = false;
    let currentSongSlug = null;
    let chartView = "full";
    let chartZoom = "normal";
    let autoScrollActive = false;
    let scrollRaf = null;
    let scrollTouchListener = null;

    function esc(s) {{
      return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
    }}

    function parseChordRoot(chord) {{
      let main = chord.trim();
      if (main.includes("/")) main = main.split("/")[0];
      const m = main.match(/^([A-G])([#b]?)(.*)$/);
      if (!m) return [chord, ""];
      let root = m[1] + m[2];
      if (FLAT_TO_SHARP[root]) root = FLAT_TO_SHARP[root];
      return [root, m[3]];
    }}

    function noteIndex(note) {{
      const [root] = parseChordRoot(note);
      return CHROMATIC.indexOf(root);
    }}

    function transposeChord(chord, semitones) {{
      if (!chord || !semitones) return chord;
      let bass = "";
      let main = chord;
      if (chord.includes("/")) {{
        const parts = chord.split("/");
        main = parts[0];
        bass = "/" + transposeChord(parts[1], semitones);
      }}
      const [root, suffix] = parseChordRoot(main);
      const idx = CHROMATIC.indexOf(root);
      if (idx < 0) return chord;
      const newRoot = CHROMATIC[(idx + semitones + 120) % 12];
      return newRoot + suffix + bass;
    }}

    function chordToNashville(chord, key) {{
      const [keyRoot] = parseChordRoot(key);
      const [chordRoot, suffix] = parseChordRoot(chord);
      const ki = CHROMATIC.indexOf(keyRoot);
      const ci = CHROMATIC.indexOf(chordRoot);
      if (ki < 0 || ci < 0) return "";
      const semi = (ci - ki + 12) % 12;
      const isMinor = suffix.startsWith("m") && !suffix.startsWith("maj");
      for (let d = 0; d < MAJOR_SCALE.length; d++) {{
        if (MAJOR_SCALE[d] === semi) {{
          const num = String(d + 1);
          if (isMinor && [2,3,6].includes(d + 1)) return num + "m";
          if (isMinor) return num + "m";
          return num;
        }}
      }}
      return "";
    }}

    function writePositionedLine(lyrics, items) {{
      if (!items.length) return "";
      const chars = Array(lyrics.length).fill(" ");
      for (const [pos, text] of items) {{
        for (let i = 0; i < text.length; i++) {{
          const idx = pos + i;
          if (idx < chars.length) chars[idx] = text[i];
          else chars.push(...Array(idx - chars.length).fill(" "), text[i]);
        }}
      }}
      return chars.join("").trimEnd();
    }}

    function entryChordLineText(entry, transpose) {{
      const parts = [];
      if (entry.chord) parts.push(transposeChord(entry.chord, transpose));
      if (entry.cue) parts.push(entry.cue);
      return parts.join(" ");
    }}

    function buildChordLine(lyrics, chords, transpose) {{
      if (!chords.length) return "";
      const items = chords.map(entry => [
        entry.pos,
        entryChordLineText(entry, transpose),
      ]).filter(([, text]) => text);
      return writePositionedLine(lyrics, items);
    }}

    function renderChordTrack(lyrics, chords, key, transpose, showNums) {{
      if (!showNums) {{
        const chordLine = buildChordLine(lyrics, chords, transpose);
        return `<div class="chords">${{esc(chordLine)}}</div>`;
      }}
      const markers = chords.map(entry => {{
        const chord = entry.chord ? transposeChord(entry.chord, transpose) : "";
        const cue = entry.cue || "";
        const numeral = chord ? chordToNashville(chord, key) : "";
        const chordHtml = chord ? `<span class="chord">${{esc(chord)}}</span>` : "";
        const cueHtml = cue ? `<span class="chord-cue">${{esc(cue)}}</span>` : "";
        const numHtml = numeral
          ? `<span class="nashville" style="width:${{chord.length}}ch">${{esc(numeral)}}</span>`
          : "";
        return `<span class="chord-marker" style="left:${{entry.pos}}ch">` +
          `${{chordHtml}}${{cueHtml}}${{numHtml}}</span>`;
      }}).join("");
      return `<div class="chord-track">${{markers}}</div>`;
    }}

    function sectionTitle(type, label, number) {{
      let title = type.replace(/_/g, "-").split("-")
        .map(word => word.charAt(0).toUpperCase() + word.slice(1)).join("-");
      if (number) title += " " + number;
      if (label) title += " — " + label;
      return title;
    }}

    function renderLyricSegments(segments, fallbackLyrics) {{
      const parts = segments && segments.length
        ? segments
        : [{{ text: fallbackLyrics || "", harmony: false, direction: false }}];
      return parts.map(segment => {{
        const text = esc(segment.text);
        if (segment.harmony) return `<span class="harmony">${{text}}</span>`;
        if (segment.direction) {{
          const css = "inline-direction";
          return segment.bold
            ? `<span class="${{css}}"><strong>${{text}}</strong></span>`
            : `<span class="${{css}}">${{text}}</span>`;
        }}
        return text;
      }}).join("");
    }}

    function renderBlock(block, key, transpose, showNums) {{
      if (block.kind === "lyric") {{
        const chordHtml = renderChordTrack(
          block.lyrics, block.chords || [], key, transpose, showNums
        );
        const lyricsHtml = renderLyricSegments(block.segments, block.lyrics);
        return `<div class="lyric-row">` +
          chordHtml +
          `<div class="lyrics">${{lyricsHtml}}</div></div>`;
      }}
      if (block.kind === "note") {{
        const css = block.inline ? "inline-direction" : "note";
        return `<p class="${{css}}">${{esc(block.text)}}</p>`;
      }}
      if (block.kind === "harmony") {{
        return `<p class="harmony-line">${{esc(block.text)}}</p>`;
      }}
      if (block.kind === "bars") {{
        return `<p class="bars">${{esc(block.text)}}</p>`;
      }}
      if (block.kind === "chord_line") {{
        const items = (block.chords || []).map(entry =>
          esc(transposeChord(entry.chord, transpose))
        ).join("  ");
        return `<p class="chord-line">${{items}}</p>`;
      }}
      if (block.kind === "tab" || block.kind === "abc") {{
        return `<h3 class="section-label">${{esc(block.label)}}</h3>` +
          `<pre class="${{block.kind}}">${{esc(block.text)}}</pre>`;
      }}
      return "";
    }}

    function renderOutlineChords(section, key, transpose, showNums) {{
      const compact = section.chord_compact || [];
      if (compact.length) {{
        return compact.map(row => {{
          const chords = (row.chords || []).map(chord => {{
            const transposed = transposeChord(chord, transpose);
            if (!showNums) return transposed;
            const numeral = chordToNashville(transposed, key);
            return numeral ? `${{transposed}} (${{numeral}})` : transposed;
          }}).join(" · ") || "—";
          const repeat = row.repeat > 1
            ? ` <span class="repeat">(×${{row.repeat}})</span>`
            : "";
          return `<p class="outline-chord-compact">${{esc(chords)}}${{repeat}}</p>`;
        }}).join("");
      }}
      const chords = (section.chords || []).map(chord => {{
        const transposed = transposeChord(chord, transpose);
        if (!showNums) return transposed;
        const numeral = chordToNashville(transposed, key);
        return numeral ? `${{transposed}} (${{numeral}})` : transposed;
      }}).join(" · ") || "—";
      return `<p class="outline-chords">${{esc(chords)}}</p>`;
    }}

    function renderSections(sections, key, transpose, showNums) {{
      let html = "";
      for (const section of sections) {{
        if (section.type === "comment") {{
          for (const block of section.blocks) {{
            html += renderBlock(block, key, transpose, showNums);
          }}
          continue;
        }}
        const hasLabel = section.type !== "comment";
        const renderable = new Set(["lyric", "note", "harmony", "bars", "chord_line", "tab", "abc"]);
        let sectionHtml = "";
        if (hasLabel && section.blocks.some(b => renderable.has(b.kind))) {{
          sectionHtml += `<h3 class="section-label">${{esc(sectionTitle(section.type, section.label, section.number))}}</h3>`;
        }}
        const blockClass = ["intro","outro"].includes(section.type) ? "note-block" : "lyric-block";
        let blockHtml = "";
        for (const block of section.blocks) {{
          blockHtml += renderBlock(block, key, transpose, showNums);
        }}
        if (blockHtml) sectionHtml += `<div class="${{blockClass}}">${{blockHtml}}</div>`;
        if (sectionHtml) {{
          html += `<section class="chart-section">${{sectionHtml}}</section>`;
        }}
      }}
      return html;
    }}

    function renderOutline(outline, key, transpose, showNums) {{
      if (!outline || !outline.length) {{
        return '<p class="note">No section breakdown available for this chart.</p>';
      }}
      return outline.map(section => {{
        const title = sectionTitle(section.type, section.label, section.number);
        const chordHtml = renderOutlineChords(section, key, transpose, showNums);
        const notes = (section.notes || []).map(note =>
          `<p class="note">${{esc(note)}}</p>`
        ).join("");
        const start = section.start
          ? `<p class="outline-hint"><span class="hint-label">Starts</span>${{esc(section.start)}}…</p>`
          : "";
        const end = section.end
          ? `<p class="outline-hint"><span class="hint-label">Ends</span>…${{esc(section.end)}}</p>`
          : "";
        return `<article class="outline-section">` +
          `<h3 class="section-label">${{esc(title)}}</h3>` +
          chordHtml +
          notes + start + end +
          `</article>`;
      }}).join("");
    }}

    function countLyricLines(sections) {{
      let count = 0;
      for (const section of sections) {{
        for (const block of section.blocks || []) {{
          if (block.kind === "lyric") count++;
        }}
      }}
      return count;
    }}

    function formatDuration(seconds) {{
      const mins = Math.floor(seconds / 60);
      const secs = Math.round(seconds % 60);
      return `${{mins}}:${{String(secs).padStart(2, "0")}}`;
    }}

    function baseScrollDuration(song) {{
      if (song.duration_seconds) return song.duration_seconds;
      if (song.tempo) {{
        const lines = countLyricLines(song.sections);
        const beatsPerLine = 4;
        return Math.max(60, lines * beatsPerLine * (60 / song.tempo));
      }}
      return 180;
    }}

    function estimateScrollDuration(song) {{
      if (song.scroll_duration_seconds) return song.scroll_duration_seconds;
      const base = baseScrollDuration(song);
      const mult = song.scroll_multiplier;
      if (mult && mult > 0 && mult !== 1) return base / mult;
      return base;
    }}

    function scrollHintText(song) {{
      const scroll = estimateScrollDuration(song);
      const parts = [`~${{formatDuration(scroll)}} scroll`];
      const track = song.duration_seconds;
      if (track && Math.abs(track - scroll) > 1) {{
        parts.push(`${{formatDuration(track)}} track`);
      }}
      if (song.scroll_multiplier && song.scroll_multiplier !== 1) {{
        parts.push(`${{song.scroll_multiplier}}×`);
      }} else if (song.scroll_duration_seconds) {{
        parts.push("custom scroll");
      }}
      if (song.tempo) parts.push(`${{song.tempo}} BPM`);
      else if (!track && !song.scroll_duration_seconds) parts.push("estimated");
      return parts.join(" · ");
    }}

    function stopAutoScroll() {{
      if (scrollRaf) {{
        cancelAnimationFrame(scrollRaf);
        scrollRaf = null;
      }}
      autoScrollActive = false;
      updateScrollButton();
    }}

    function updateScrollButton() {{
      const btn = document.getElementById("btn-scroll");
      if (!btn) return;
      btn.textContent = autoScrollActive ? "⏸ Pause" : "▶ Scroll";
      btn.classList.toggle("primary", autoScrollActive);
    }}

    function attachScrollTouchPause() {{
      if (scrollTouchListener) return;
      scrollTouchListener = () => {{
        if (autoScrollActive) stopAutoScroll();
      }};
      window.addEventListener("touchstart", scrollTouchListener, {{ passive: true }});
      window.addEventListener("wheel", scrollTouchListener, {{ passive: true }});
    }}

    function startAutoScroll(song) {{
      stopAutoScroll();
      const body = document.getElementById("chart-body");
      if (!body) return;
      const bodyTop = body.getBoundingClientRect().top + window.scrollY;
      const bodyBottom = bodyTop + body.offsetHeight;
      const viewportBottom = window.scrollY + window.innerHeight - 72;
      const distance = Math.max(0, bodyBottom - viewportBottom);
      if (distance <= 0) return;

      const startY = window.scrollY;
      const durationMs = estimateScrollDuration(song) * 1000;
      const started = performance.now();
      autoScrollActive = true;
      updateScrollButton();

      function tick(now) {{
        if (!autoScrollActive) return;
        const elapsed = now - started;
        const progress = Math.min(elapsed / durationMs, 1);
        window.scrollTo(0, startY + distance * progress);
        if (progress < 1) {{
          scrollRaf = requestAnimationFrame(tick);
        }} else {{
          stopAutoScroll();
        }}
      }}
      scrollRaf = requestAnimationFrame(tick);
    }}

    function toggleAutoScroll() {{
      const song = currentSongSlug ? songBySlug(currentSongSlug) : null;
      if (!song) return;
      if (autoScrollActive) {{
        stopAutoScroll();
      }} else {{
        startAutoScroll(song);
      }}
    }}

    function applyChartZoom() {{
      const body = document.getElementById("chart-body");
      if (!body) return;
      body.style.zoom = "";
      if (chartZoom !== "fit" || chartView !== "full") return;
      requestAnimationFrame(() => {{
        const available = window.innerHeight - 220;
        const natural = body.scrollHeight;
        if (natural <= 0) return;
        const scale = Math.min(1, available / natural);
        body.style.zoom = String(scale);
      }});
    }}

    function renderChartContent(song, keyDisplay, transpose) {{
      if (chartView === "outline") {{
        return renderOutline(song.outline, keyDisplay, transpose, showNashville);
      }}
      return renderSections(song.sections, keyDisplay, transpose, showNashville);
    }}

    function displayKey(song, transpose) {{
      return transposeChord(song.key, transpose);
    }}

    function songBySlug(slug) {{
      return GIG.songs.find(s => s.slug === slug);
    }}

    function songIndex(slug) {{
      return GIG.songs.findIndex(s => s.slug === slug);
    }}

    function matchingSongs(query) {{
      const q = query.trim().toLowerCase();
      if (!q) return [];
      return GIG.songs.filter(s =>
        s.title.toLowerCase().includes(q) ||
        (s.artist && s.artist.toLowerCase().includes(q))
      );
    }}

    function clearSearch() {{
      searchInput.value = "";
      suggestions.innerHTML = "";
    }}

    function renderSuggestions(query) {{
      const matches = matchingSongs(query).slice(0, 12);
      suggestions.innerHTML = matches.map(song =>
        `<button type="button" class="suggestion" data-slug="${{song.slug}}">` +
        `<span class="title">${{song.number}}. ${{song.title}}</span>` +
        `<span class="meta">Set ${{song.set}} · ${{song.key}}</span>` +
        `</button>`
      ).join("");
    }}

    function renderSongList(anchorSet) {{
      const q = searchInput.value.trim().toLowerCase();
      let html = "";
      for (const set of GIG.sets) {{
        const songs = set.songs.filter(s =>
          !q || s.title.toLowerCase().includes(q) ||
          (s.artist && s.artist.toLowerCase().includes(q))
        );
        if (!songs.length) continue;
        html += `<div class="set-header" id="set-${{set.number}}">Set ${{set.number}}</div>`;
        for (const song of songs) {{
          html += `<a class="song-link" href="#/song/${{song.slug}}">` +
            `<span class="num">${{song.number}}.</span>${{song.title}}` +
            `<span class="key">${{song.key}}</span></a>`;
        }}
      }}
      songList.innerHTML = html || `<p class="note">No songs match.</p>`;
      if (anchorSet) {{
        document.getElementById(`set-${{anchorSet}}`)?.scrollIntoView({{ behavior: "smooth", block: "start" }});
      }}
    }}

    function showList(anchorSet) {{
      stopAutoScroll();
      clearSearch();
      listView.classList.remove("hidden");
      songView.classList.add("hidden");
      navTop.classList.add("hidden");
      navBottom.classList.add("hidden");
      renderSongList(anchorSet);
    }}

    searchInput.addEventListener("input", () => {{
      renderSuggestions(searchInput.value);
      renderSongList();
    }});

    searchInput.addEventListener("focus", () => {{
      renderSuggestions(searchInput.value);
    }});

    suggestions.addEventListener("click", (e) => {{
      const btn = e.target.closest(".suggestion");
      if (!btn) return;
      location.hash = "#/song/" + btn.dataset.slug;
    }});

    function renderSong(slug) {{
      const song = songBySlug(slug);
      if (!song) {{ showList(); return; }}
      stopAutoScroll();
      clearSearch();
      currentSongSlug = slug;
      const transpose = transposeOffsets[slug] || 0;
      listView.classList.add("hidden");
      songView.classList.remove("hidden");
      navTop.classList.remove("hidden");
      navBottom.classList.remove("hidden");
      const keyDisplay = displayKey(song, transpose);
      const transposeLabel = transpose === 0 ? "" : ` (${{transpose > 0 ? "+" : ""}}${{transpose}})`;
      songView.innerHTML =
        `<div class="song-header">` +
        `<h1>${{song.number}}. ${{esc(song.title)}}</h1>` +
        `<p class="artist">Set ${{song.set}}${{song.artist ? " · " + esc(song.artist) : ""}}</p>` +
        `</div>` +
        `<div class="transpose-bar">` +
        `<span class="key-label">Key: ${{esc(keyDisplay)}}${{transposeLabel}}</span>` +
        `<button type="button" id="tp-down" title="Down half step">−</button>` +
        `<button type="button" class="reset" id="tp-reset">Reset</button>` +
        `<button type="button" id="tp-up" title="Up half step">+</button>` +
        `<label class="nashville"><input type="checkbox" id="tp-nashville" ${{showNashville ? "checked" : ""}}> Nashville #</label>` +
        `</div>` +
        `<div class="performance-bar">` +
        `<div class="perf-group">` +
        `<button type="button" class="perf-btn ${{chartView === "full" ? "active" : ""}}" id="view-full">Full</button>` +
        `<button type="button" class="perf-btn ${{chartView === "outline" ? "active" : ""}}" id="view-outline">Structure</button>` +
        `</div>` +
        `<div class="perf-group">` +
        `<button type="button" class="perf-btn ${{chartZoom === "normal" ? "active" : ""}}" id="zoom-normal">Normal</button>` +
        `<button type="button" class="perf-btn ${{chartZoom === "fit" ? "active" : ""}}" id="zoom-fit">Fit page</button>` +
        `</div>` +
        `<p class="scroll-hint">Auto scroll: ${{esc(scrollHintText(song))}}</p>` +
        `</div>` +
        `<div id="chart-body" class="chart-body">` +
        renderChartContent(song, keyDisplay, transpose) +
        `</div>`;
      document.getElementById("tp-down").onclick = () => {{
        transposeOffsets[slug] = (transposeOffsets[slug] || 0) - 1;
        renderSong(slug);
      }};
      document.getElementById("tp-up").onclick = () => {{
        transposeOffsets[slug] = (transposeOffsets[slug] || 0) + 1;
        renderSong(slug);
      }};
      document.getElementById("tp-reset").onclick = () => {{
        transposeOffsets[slug] = 0;
        renderSong(slug);
      }};
      document.getElementById("tp-nashville").onchange = (e) => {{
        showNashville = e.target.checked;
        renderSong(slug);
      }};
      document.getElementById("view-full").onclick = () => {{
        chartView = "full";
        renderSong(slug);
      }};
      document.getElementById("view-outline").onclick = () => {{
        chartView = "outline";
        chartZoom = "normal";
        renderSong(slug);
      }};
      document.getElementById("zoom-normal").onclick = () => {{
        chartZoom = "normal";
        renderSong(slug);
      }};
      document.getElementById("zoom-fit").onclick = () => {{
        chartZoom = "fit";
        chartView = "full";
        renderSong(slug);
      }};
      updateScrollButton();
      applyChartZoom();
      attachScrollTouchPause();
      window.scrollTo(0, 0);
    }}

    function route() {{
      const hash = location.hash.replace(/^#\\/?/, "");
      if (hash.startsWith("song/")) {{
        renderSong(hash.slice(5));
      }} else {{
        const anchor = hash.startsWith("set/") ? hash.slice(4) : null;
        showList(anchor);
      }}
    }}

    function goNext() {{
      const hash = location.hash;
      if (!hash.includes("song/")) return;
      const slug = hash.split("song/")[1];
      const idx = songIndex(slug);
      if (idx >= 0 && idx < GIG.songs.length - 1) {{
        location.hash = "#/song/" + GIG.songs[idx + 1].slug;
      }}
    }}

    function goPrev() {{
      const hash = location.hash;
      if (!hash.includes("song/")) return;
      const slug = hash.split("song/")[1];
      const idx = songIndex(slug);
      if (idx > 0) {{
        location.hash = "#/song/" + GIG.songs[idx - 1].slug;
      }}
    }}

    document.getElementById("btn-prev").onclick = goPrev;
    document.getElementById("btn-next").onclick = goNext;
    document.getElementById("btn-next-bottom").onclick = goNext;
    document.getElementById("btn-scroll").onclick = toggleAutoScroll;
    document.getElementById("btn-setlist").onclick = () => {{ location.hash = "#/"; }};
    document.getElementById("btn-jump-set").onclick = () => {{
      const hash = location.hash;
      if (!hash.includes("song/")) return;
      const song = songBySlug(hash.split("song/")[1]);
      if (song) location.hash = "#/set/" + song.set;
    }};

    window.addEventListener("hashchange", route);
    route();
  </script>
</body>
</html>
"""
