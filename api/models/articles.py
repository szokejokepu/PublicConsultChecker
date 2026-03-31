"""Pydantic models for article-related endpoints."""

from __future__ import annotations

from pydantic import BaseModel


class AnalysisOut(BaseModel):
    keyword_matched: bool
    matched_keywords: list[str]
    is_public_consultation: bool | None
    classifier_score: float | None
    extracted_date: str | None
    extracted_time: str | None
    extracted_place: str | None
    extracted_subject: str | None
    processed_at: str


class ArticleOut(BaseModel):
    id: int
    url: str
    title: str | None
    author: str | None
    date: str | None
    content: str | None
    source_url: str | None
    scraped_at: str
    analysis: AnalysisOut | None = None


class ArticleListOut(BaseModel):
    articles: list[ArticleOut]
    total: int


class StatsOut(BaseModel):
    total_articles: int
    unique_sources: int
    newest_scraped_at: str | None
