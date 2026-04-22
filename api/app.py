"""FastAPI application — REST API + static frontend."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from api.routes.articles import router as articles_router
from api.routes.process import router as process_router
from api.routes.scrape import router as scrape_router
from api.routes.scheduler import router as scheduler_router
from api.scheduler import create_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = create_scheduler()
    if scheduler:
        scheduler.start()
    yield
    if scheduler:
        scheduler.shutdown(wait=False)


app = FastAPI(title="Article Scraper API", lifespan=lifespan)

app.include_router(articles_router)
app.include_router(scrape_router)
app.include_router(process_router)
app.include_router(scheduler_router)

FRONTEND_DIR = Path(__file__).parent.parent / "rag-front" / "dist"

if FRONTEND_DIR.exists():
    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(FRONTEND_DIR / "index.html")

    @app.get("/favicon.svg", include_in_schema=False)
    def favicon():
        return FileResponse(FRONTEND_DIR / "favicon.svg")

    @app.get("/icons.svg", include_in_schema=False)
    def icons():
        return FileResponse(FRONTEND_DIR / "icons.svg")

    app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="assets")
