"""Article endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from api.dependencies import db
from api.models.articles import AnalysisOut, ArticleListOut, ArticleOut, StatsOut

router = APIRouter(prefix="/api")


@router.get("/articles", response_model=ArticleListOut)
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


@router.get("/articles/{article_id}", response_model=ArticleOut)
def get_article(article_id: int):
    article = db.get_article(article_id)
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")
    analysis = db.get_analysis(article_id)
    return _to_out(article, analysis)


@router.post("/articles/{article_id}/process", response_model=AnalysisOut)
def process_article(article_id: int):
    article = db.get_article(article_id)
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")
    from pipeline.runner import process_single
    result = process_single(article, db)
    return AnalysisOut(
        keyword_matched=result.keyword_matched,
        matched_keywords=result.matched_keywords,
        is_public_consultation=result.is_public_consultation,
        classifier_score=result.classifier_score,
        extracted_date=result.extracted_date,
        extracted_time=result.extracted_time,
        extracted_place=result.extracted_place,
        extracted_subject=result.extracted_subject,
        processed_at=result.processed_at,
    )


@router.delete("/articles/{article_id}")
def delete_article(article_id: int):
    removed = db.delete_article(article_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Article not found")
    return {"deleted": article_id}


@router.get("/stats", response_model=StatsOut)
def get_stats():
    return db.get_stats()


def _to_out(a, analysis=None) -> ArticleOut:
    analysis_out = None
    if analysis is not None:
        analysis_out = AnalysisOut(
            keyword_matched=analysis.keyword_matched,
            matched_keywords=analysis.matched_keywords,
            is_public_consultation=analysis.is_public_consultation,
            classifier_score=analysis.classifier_score,
            extracted_date=analysis.extracted_date,
            extracted_time=analysis.extracted_time,
            extracted_place=analysis.extracted_place,
            extracted_subject=analysis.extracted_subject,
            processed_at=analysis.processed_at,
        )
    return ArticleOut(
        id=a.id,
        url=a.url,
        title=a.title,
        author=a.author,
        date=a.date,
        content=a.content,
        source_url=a.source_url,
        scraped_at=a.scraped_at,
        analysis=analysis_out,
    )
