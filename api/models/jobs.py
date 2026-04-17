"""Pydantic models for job-related endpoints."""

from __future__ import annotations

from pydantic import BaseModel, Field

from scraper.config import (
    DEFAULT_ARTICLE_LINK_SELECTOR,
    DEFAULT_PAGE_PREFIX,
    DEFAULT_PAGE_SEPARATOR,
    DEFAULT_PAGE_SUFFIX,
    DEFAULT_WORKERS,
)


class ScrapeRequest(BaseModel):
    url: str
    selector: str = DEFAULT_ARTICLE_LINK_SELECTOR
    max_pages: int | None = None
    workers: int = Field(default=DEFAULT_WORKERS, ge=1, le=32)
    page_separator: str = DEFAULT_PAGE_SEPARATOR
    page_prefix: str = DEFAULT_PAGE_PREFIX
    page_suffix: str = DEFAULT_PAGE_SUFFIX


class ProcessRequest(BaseModel):
    batch_size: int = Field(default=32, ge=1, le=500)
    use_keyword_filter: bool = True
    reprocess_all: bool = False


class JobOut(BaseModel):
    job_id: str
    status: str
    summary: dict
    error: str | None
