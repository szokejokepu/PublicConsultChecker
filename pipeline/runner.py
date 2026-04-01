"""Orchestrates the NLP pipeline: reads unprocessed articles, writes analysis rows."""

from __future__ import annotations

from datetime import datetime

from scraper.database import ArticleDB

from .classifier import classify
from .keyword_filter import keyword_filter
from .models import AnalysisResult
from .ner import extract_entities
from .normalizer import normalize


def process_single(article, db: ArticleDB, use_keyword_filter: bool = True) -> AnalysisResult:
    """Process or reprocess a single article, overwriting any existing analysis."""
    processed_at = datetime.utcnow().isoformat()
    text = article.content or ""
    normalized, lowered = normalize(text)
    kw_matched, keywords = keyword_filter(lowered)

    if use_keyword_filter and not kw_matched:
        result = AnalysisResult(
            article_id=article.id,
            keyword_matched=False,
            matched_keywords=[],
            is_public_consultation=None,
            classifier_score=None,
            extracted_date=None,
            extracted_time=None,
            extracted_place=None,
            extracted_subject=None,
            processed_at=processed_at,
        )
    else:
        is_positive, score = classify(normalized)
        entities = extract_entities(text)
        result = AnalysisResult(
            article_id=article.id,
            keyword_matched=kw_matched,
            matched_keywords=keywords,
            is_public_consultation=is_positive,
            classifier_score=score,
            extracted_date=entities["extracted_date"],
            extracted_time=entities["extracted_time"],
            extracted_place=entities["extracted_place"],
            extracted_subject=entities["extracted_subject"],
            processed_at=processed_at,
        )

    db.save_analysis(result)
    return result


def run_pipeline(
    db: ArticleDB,
    batch_size: int = 32,
    verbose: bool = True,
    use_keyword_filter: bool = True,
) -> dict:
    """Process all articles not yet in article_analysis.

    Returns a summary dict with keys ``processed``, ``matched``,
    ``classified_positive``.
    """
    articles = db.list_unprocessed(limit=batch_size)
    processed = 0
    matched = 0
    classified_positive = 0

    for article in articles:
        processed_at = datetime.utcnow().isoformat()
        text = article.content or ""
        normalized, lowered = normalize(text)

        kw_matched, keywords = keyword_filter(lowered)

        if use_keyword_filter and not kw_matched:
            db.save_analysis(
                AnalysisResult(
                    article_id=article.id,
                    keyword_matched=False,
                    matched_keywords=[],
                    is_public_consultation=None,
                    classifier_score=None,
                    extracted_date=None,
                    extracted_time=None,
                    extracted_place=None,
                    extracted_subject=None,
                    processed_at=processed_at,
                )
            )
            processed += 1
            if verbose:
                print(f"[pipeline] article #{article.id}: no keyword match — skipped")
            continue

        if kw_matched:
            matched += 1
        is_positive, score = classify(normalized)
        entities = extract_entities(text)

        if is_positive:
            classified_positive += 1

        db.save_analysis(
            AnalysisResult(
                article_id=article.id,
                keyword_matched=kw_matched,
                matched_keywords=keywords,
                is_public_consultation=is_positive,
                classifier_score=score,
                extracted_date=entities["extracted_date"],
                extracted_time=entities["extracted_time"],
                extracted_place=entities["extracted_place"],
                extracted_subject=entities["extracted_subject"],
                processed_at=processed_at,
            )
        )
        processed += 1
        if verbose:
            label = "YES" if is_positive else "NO"
            print(
                f"[pipeline] article #{article.id}: keywords={keywords} "
                f"consultation={label} score={score:.3f}"
            )

    return {
        "processed": processed,
        "matched": matched,
        "classified_positive": classified_positive,
    }
