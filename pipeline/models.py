"""Data model for NLP pipeline results."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AnalysisResult:
    article_id: int
    keyword_matched: bool
    matched_keywords: list[str]
    is_public_consultation: bool | None  # None = keyword filter skipped classification
    classifier_score: float | None
    extracted_date: str | None
    extracted_time: str | None
    extracted_place: str | None
    extracted_subject: str | None
    processed_at: str
    notified_at: str | None = None
