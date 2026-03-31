"""Scrape job endpoints."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, HTTPException

from api.dependencies import db
from api.jobs import JobStatus, registry
from api.models.jobs import JobOut, ScrapeRequest
from scraper.crawler import crawl_paginated

router = APIRouter(prefix="/api")


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


def _job_to_out(job) -> JobOut:
    return JobOut(
        job_id=job.id,
        status=job.status.value,
        summary=job.summary,
        error=job.error,
    )
