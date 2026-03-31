"""FastAPI application — REST API + static frontend."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from api.routes.articles import router as articles_router
from api.routes.process import router as process_router
from api.routes.scrape import router as scrape_router

app = FastAPI(title="Article Scraper API")

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
# FRONTEND_DIR = Path(__file__).parent.parent / "rag-front" / "dist"


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(FRONTEND_DIR / "index.html")


# app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="assets")
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

app.include_router(articles_router)
app.include_router(scrape_router)
app.include_router(process_router)
