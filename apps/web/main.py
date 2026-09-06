from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from music_gigs.export import render_catalog_review, render_catalog_review_pdf, render_csv, render_text
from music_gigs.loader import discover_bands, format_duration, load_band
from music_gigs.models import DEFAULT_TEXT_TEMPLATE, EXPORT_COLUMNS, GigConfig
from music_gigs.orderer import build_setlist, reorder_setlist
from music_gigs.picker import auto_fill_setlist

ROOT = Path(__file__).resolve().parents[2]
WEB_DIR = Path(__file__).resolve().parent

app = FastAPI(title="Music Gigs")
app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")
templates = Jinja2Templates(directory=WEB_DIR / "templates")


def _get_band(slug: str):
    for band in discover_bands(ROOT):
        if band.slug == slug or band.directory == slug:
            return band
    raise HTTPException(status_code=404, detail="Band not found")


def _parse_columns(columns: list[str] | None) -> list[str]:
    if not columns:
        return [col.id for col in EXPORT_COLUMNS if col.default]
    return columns


def _setlist_context(band, setlist):
    return {
        "band": band,
        "setlist": setlist,
        "sets": setlist.sets,
        "format_duration": format_duration,
        "total_duration": format_duration(setlist.total_duration_seconds),
    }


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    bands = discover_bands(ROOT)
    return templates.TemplateResponse(
        request,
        "index.html",
        {"bands": bands},
    )


@app.get("/bands/{slug}", response_class=HTMLResponse)
async def band_page(request: Request, slug: str):
    band = _get_band(slug)
    return templates.TemplateResponse(
        request,
        "band.html",
        {
            "band": band,
            "export_columns": EXPORT_COLUMNS,
            "default_template": DEFAULT_TEXT_TEMPLATE,
        },
    )


@app.post("/bands/{slug}/generate", response_class=HTMLResponse)
async def generate_setlist(
    request: Request,
    slug: str,
    duration_minutes: int = Form(90),
    absent_members: Annotated[list[str], Form()] = [],
):
    band = _get_band(slug)
    config = GigConfig(
        duration_minutes=duration_minutes,
        absent_members=absent_members,
    )
    seed = random.randint(0, 2**31 - 1)
    picked, filter_warnings = auto_fill_setlist(band, config, seed=seed)
    setlist = build_setlist(
        band, picked, duration_minutes, filter_warnings, seed=seed
    )
    return templates.TemplateResponse(
        request,
        "partials/setlist.html",
        {
            "seed": seed,
            **_setlist_context(band, setlist),
        },
    )


@app.post("/bands/{slug}/reorder", response_class=HTMLResponse)
async def reorder(
    request: Request,
    slug: str,
    duration_minutes: int = Form(90),
    order_data: str = Form(...),
):
    band = _get_band(slug)
    data = json.loads(order_data)
    titles = [item["title"] for item in data]
    set_numbers = [int(item["set"]) for item in data]
    setlist = reorder_setlist(band, titles, set_numbers, duration_minutes)
    return templates.TemplateResponse(
        request,
        "partials/setlist.html",
        _setlist_context(band, setlist),
    )


@app.get("/bands/{slug}/catalog.pdf")
async def export_catalog_pdf(slug: str):
    band = _get_band(slug)
    pdf_bytes = render_catalog_review_pdf(band)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{band.slug}-catalog.pdf"',
        },
    )


@app.get("/bands/{slug}/catalog.txt")
async def export_catalog(slug: str):
    band = _get_band(slug)
    text = render_catalog_review(band)
    return PlainTextResponse(
        text,
        media_type="text/plain",
        headers={
            "Content-Disposition": f'attachment; filename="{band.slug}-catalog.txt"',
        },
    )


@app.get("/bands/{slug}/export.txt")
async def export_txt(
    slug: str,
    duration_minutes: int = 90,
    absent_members: list[str] | None = None,
    columns: list[str] | None = None,
    template: str = DEFAULT_TEXT_TEMPLATE,
    seed: int | None = None,
):
    band = _get_band(slug)
    config = GigConfig(
        duration_minutes=duration_minutes,
        absent_members=absent_members or [],
    )
    picked, _ = auto_fill_setlist(band, config, seed=seed)
    setlist = build_setlist(band, picked, duration_minutes, seed=seed)
    if columns:
        text = render_text(band, setlist, columns=columns)
    else:
        text = render_text(band, setlist, template=template)
    return PlainTextResponse(text, media_type="text/plain")


@app.get("/bands/{slug}/export.csv")
async def export_csv(
    slug: str,
    duration_minutes: int = 90,
    absent_members: list[str] | None = None,
    columns: list[str] | None = None,
    seed: int | None = None,
):
    band = _get_band(slug)
    config = GigConfig(
        duration_minutes=duration_minutes,
        absent_members=absent_members or [],
    )
    picked, _ = auto_fill_setlist(band, config, seed=seed)
    setlist = build_setlist(band, picked, duration_minutes, seed=seed)
    csv_content = render_csv(band, setlist, columns=_parse_columns(columns))
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{band.slug}-setlist.csv"'},
    )


def run():
    import uvicorn

    uvicorn.run("apps.web.main:app", host="127.0.0.1", port=8000, reload=True)
