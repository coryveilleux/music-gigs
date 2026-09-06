from __future__ import annotations

import json
from pathlib import Path

import yaml

from music_gigs.chordpro import parse_chordpro, render_chordpro_html
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

            song_index += 1
            song_obj = {
                "slug": slug,
                "title": title,
                "artist": artist,
                "key": key,
                "set": set_number,
                "number": song_index,
                "html": render_chordpro_html(parsed),
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


def render_gig_html(gig_data: dict) -> str:
    payload = json.dumps(gig_data, ensure_ascii=False)
    payload = payload.replace("</", "<\\/")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <meta name="apple-mobile-web-app-capable" content="yes">
  <title>{gig_data["band"]} — {gig_data["gig"]}</title>
  <style>
    :root {{
      --bg: #111;
      --surface: #1a1a1a;
      --text: #f2f2f2;
      --muted: #aaa;
      --accent: #f5c542;
      --border: #333;
      --tap: 48px;
    }}
    * {{ box-sizing: border-box; }}
    html, body {{ margin: 0; padding: 0; background: var(--bg); color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, sans-serif; }}
    .hidden {{ display: none !important; }}
    .nav-bar {{
      position: fixed; left: 0; right: 0; z-index: 100;
      display: flex; gap: 0.5rem; padding: 0.5rem;
      background: rgba(17,17,17,0.95); border-bottom: 1px solid var(--border);
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
    .nav-bar button.primary {{ background: var(--accent); color: #111; border-color: var(--accent); font-weight: 600; }}
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
    .suggestion:active, .suggestion:hover {{ background: #252525; }}
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
    .song-header .artist {{ color: var(--muted); margin-bottom: 1rem; }}
    .section-label {{
      color: var(--accent); font-size: 0.95rem; text-transform: uppercase;
      letter-spacing: 0.04em; margin: 1.25rem 0 0.5rem;
    }}
    .lyric-row {{
      font-family: "Courier New", Courier, monospace;
      font-size: 1.1rem; margin-bottom: 1rem;
    }}
    .lyric-row .chords {{
      color: var(--accent); font-weight: 700;
      min-height: 1.35em; white-space: pre; overflow-x: auto;
    }}
    .lyric-row .lyrics {{
      color: var(--text); white-space: pre-wrap; line-height: 1.5;
    }}
    .lyric-row.lyrics-only .lyrics {{ margin-top: 0; }}
    .note, .note-block .note {{ color: #ccc; font-style: italic; margin: 0.5rem 0; }}
    pre.tab, pre.abc {{
      background: #0a0a0a; border: 1px solid var(--border);
      border-radius: 8px; padding: 0.75rem; overflow-x: auto;
      font-family: "Courier New", Courier, monospace;
      font-size: 0.95rem; line-height: 1.35; color: #ddd;
    }}
    pre.abc {{ border-color: #445; }}
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
      <h1 id="band-name"></h1>
      <p class="meta" id="gig-meta"></p>
      <div class="search-wrap">
        <input class="search" id="search" type="search" placeholder="Search songs..." autocomplete="off" enterkeyhint="search">
        <div class="search-suggestions" id="search-suggestions"></div>
      </div>
      <div id="song-list"></div>
    </div>
    <div id="song-view" class="hidden"></div>
  </main>

  <div id="nav-bottom" class="nav-bar nav-bottom hidden">
    <button type="button" id="btn-top">Top</button>
    <button type="button" id="btn-jump-set">This set</button>
    <button type="button" id="btn-next-bottom">Next ▶</button>
  </div>

  <script>
    const GIG = {payload};

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
      clearSearch();
      listView.classList.add("hidden");
      songView.classList.remove("hidden");
      navTop.classList.remove("hidden");
      navBottom.classList.remove("hidden");
      songView.innerHTML =
        `<div class="song-header">` +
        `<h1>${{song.number}}. ${{song.title}}</h1>` +
        `<p class="artist">Set ${{song.set}} · Key ${{song.key}}${{song.artist ? " · " + song.artist : ""}}</p>` +
        `</div>` +
        song.html;
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
    document.getElementById("btn-setlist").onclick = () => {{ location.hash = "#/"; }};
    document.getElementById("btn-top").onclick = () => {{ location.hash = "#/"; }};
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
