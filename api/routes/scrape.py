"""Scrape job endpoints."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, HTTPException

from api.dependencies import db
from api.jobs import JobStatus, registry
from api.models.jobs import CrawlSessionOut, JobOut, ScrapeRequest
from scraper.crawler import crawl_paginated

router = APIRouter(prefix="/api")


def _run_scrape(job_id: str, req: ScrapeRequest) -> None:
    registry.update(job_id, JobStatus.RUNNING)
    session_id = db.create_crawl_session(
        triggered_at=datetime.now(timezone.utc).isoformat(),
        trigger_source="manual",
        config_url=req.url,
    )
    try:
        summary = crawl_paginated(
            req.url,
            db,
            selector=req.selector,
            max_pages=req.max_pages,
            max_workers=req.workers,
            page_separator=req.page_separator,
            page_prefix=req.page_prefix,
            page_suffix=req.page_suffix,
            verbose=False,
        )
        db.finish_crawl_session(session_id, summary)
        db.link_articles_to_session(session_id, summary["article_ids"])
        registry.update(job_id, JobStatus.DONE, summary=summary)
    except Exception as exc:
        db.fail_crawl_session(session_id, str(exc))
        registry.update(job_id, JobStatus.FAILED, error=str(exc))


@router.post("/scrape", response_model=JobOut, status_code=202)
def start_scrape(req: ScrapeRequest, background_tasks: BackgroundTasks):
    job = registry.create()
    background_tasks.add_task(_run_scrape, job.id, req)
    return _job_to_out(job)


@router.get("/scrape/{job_id}", response_model=JobOut)
def get_scrape_job(job_id: str):
    job = registry.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_to_out(job)


@router.get("/crawl-sessions", response_model=list[CrawlSessionOut])
def list_crawl_sessions(limit: int = 50, offset: int = 0):
    sessions = db.list_crawl_sessions(limit=limit, offset=offset)
    return [_session_to_out(s) for s in sessions]


def _job_to_out(job) -> JobOut:
    return JobOut(
        job_id=job.id,
        status=job.status.value,
        summary=job.summary,
        error=job.error,
    )


def _session_to_out(s) -> CrawlSessionOut:
    return CrawlSessionOut(
        id=s.id,
        triggered_at=s.triggered_at,
        trigger_source=s.trigger_source,
        config_url=s.config_url,
        status=s.status,
        finished_at=s.finished_at,
        saved=s.saved,
        skipped=s.skipped,
        failed=s.failed,
        error=s.error,
    )
