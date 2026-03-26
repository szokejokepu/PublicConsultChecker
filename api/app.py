"""FastAPI application — REST API + static frontend."""

from __future__ import annotations

import concurrent.futures
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from scraper.config import DEFAULT_ARTICLE_LINK_SELECTOR, DEFAULT_WORKERS
from scraper.crawler import crawl_paginated
from scraper.database import ArticleDB

from .jobs import JobStatus, registry

# ---------------------------------------------------------------------------
# Shared DB instance
# ---------------------------------------------------------------------------

DB_PATH = Path(__file__).parent.parent / "articles.db"
db = ArticleDB(db_path=DB_PATH)

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class ArticleOut(BaseModel):
    id: int
    url: str
    title: str | None
    author: str | None
    date: str | None
    content: str | None
    source_url: str | None
    scraped_at: str


class ArticleListOut(BaseModel):
    articles: list[ArticleOut]
    total: int


class StatsOut(BaseModel):
    total_articles: int
    unique_sources: int
    newest_scraped_at: str | None


class ScrapeRequest(BaseModel):
    url: str
    selector: str = DEFAULT_ARTICLE_LINK_SELECTOR
    max_pages: int | None = None
    workers: int = Field(default=DEFAULT_WORKERS, ge=1, le=32)


class JobOut(BaseModel):
    job_id: str
    status: str
    summary: dict
    error: str | None


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="Article Scraper API")

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(FRONTEND_DIR / "index.html")


app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


# ---------------------------------------------------------------------------
# Articles
# ---------------------------------------------------------------------------


@app.get("/api/articles", response_model=ArticleListOut)
def list_articles(limit: int = 50, offset: int = 0, search: str = ""):
    if search:
        articles = db.search_articles(search, limit=limit)
    else:
        articles = db.list_articles(limit=limit, offset=offset)
    stats = db.get_stats()
    return ArticleListOut(
        articles=[_to_out(a) for a in articles],
        total=stats["total_articles"],
    )


@app.get("/api/articles/{article_id}", response_model=ArticleOut)
def get_article(article_id: int):
    article = db.get_article(article_id)
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")
    return _to_out(article)


@app.delete("/api/articles/{article_id}")
def delete_article(article_id: int):
    removed = db.delete_article(article_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Article not found")
    return {"deleted": article_id}


@app.get("/api/stats", response_model=StatsOut)
def get_stats():
    return db.get_stats()


# ---------------------------------------------------------------------------
# Scrape jobs
# ---------------------------------------------------------------------------


def _run_scrape(job_id: str, req: ScrapeRequest) -> None:
    registry.update(job_id, JobStatus.RUNNING)
    try:
        summary = crawl_paginated(
            req.url,
            db,
            selector=req.selector,
            max_pages=req.max_pages,
            max_workers=req.workers,
            verbose=False,
        )
        registry.update(job_id, JobStatus.DONE, summary=summary)
    except Exception as exc:
        registry.update(job_id, JobStatus.FAILED, error=str(exc))


_thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=4)


@app.post("/api/scrape", response_model=JobOut, status_code=202)
def start_scrape(req: ScrapeRequest, background_tasks: BackgroundTasks):
    job = registry.create()
    background_tasks.add_task(_run_scrape, job.id, req)
    return _job_to_out(job)


@app.get("/api/scrape/{job_id}", response_model=JobOut)
def get_job(job_id: str):
    job = registry.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_to_out(job)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_out(a) -> ArticleOut:
    return ArticleOut(
        id=a.id,
        url=a.url,
        title=a.title,
        author=a.author,
        date=a.date,
        content=a.content,
        source_url=a.source_url,
        scraped_at=a.scraped_at,
    )


def _job_to_out(job) -> JobOut:
    return JobOut(
        job_id=job.id,
        status=job.status.value,
        summary=job.summary,
        error=job.error,
    )
