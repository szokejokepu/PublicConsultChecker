"""Tests for the NLP pipeline."""

from __future__ import annotations

import json
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from pipeline.keyword_filter import keyword_filter
from pipeline.models import AnalysisResult
from pipeline.normalizer import normalize
from scraper.database import ArticleDB


# ---------------------------------------------------------------------------
# Normalizer
# ---------------------------------------------------------------------------


def test_normalizer_strips_html():
    html = "<p>Hello <b>world</b>!</p>"
    norm, low = normalize(html)
    assert "<" not in norm
    assert "Hello" in norm
    assert "world" in norm


def test_normalizer_collapses_whitespace():
    text = "foo   bar\t\tbaz"
    norm, _ = normalize(text)
    assert "  " not in norm
    assert "foo bar" in norm


def test_normalizer_returns_lowercased_copy():
    _, low = normalize("<p>Consultare Publică</p>")
    assert low == low.lower()


# ---------------------------------------------------------------------------
# Keyword filter
# ---------------------------------------------------------------------------


def test_keyword_filter_match():
    text = "se anunță o dezbatere publică privind proiectul"
    matched, keywords = keyword_filter(text)
    assert matched is True
    assert "dezbatere publică" in keywords


def test_keyword_filter_no_match():
    text = "știri locale despre infrastructură"
    matched, keywords = keyword_filter(text)
    assert matched is False
    assert keywords == []


def test_keyword_filter_multiple_matches():
    text = "consultare publică și audiere publică"
    matched, keywords = keyword_filter(text)
    assert matched is True
    assert "consultare publică" in keywords
    assert "audiere publică" in keywords


# ---------------------------------------------------------------------------
# Classifier (mocked BERT)
# ---------------------------------------------------------------------------


def test_classifier_returns_score():
    # Mock classify entirely so torch is never imported
    with patch("pipeline.classifier.classify", return_value=(True, 0.75)) as mock_cls:
        from pipeline.classifier import classify
        result = classify("test text")
    assert isinstance(result, tuple)
    assert len(result) == 2
    label, score = result
    assert isinstance(label, bool)
    assert isinstance(score, float)


# ---------------------------------------------------------------------------
# NER (mocked transformers pipeline)
# ---------------------------------------------------------------------------


def test_ner_maps_labels():
    fake_entities = [
        {"entity_group": "DATE", "word": "15 martie 2024"},
        {"entity_group": "TIME", "word": "10:00"},
        {"entity_group": "LOC", "word": "Cluj-Napoca"},
    ]

    with patch("pipeline.ner._ner_pipeline", fake_entities.__iter__):
        # Patch _load to return a callable that yields our fake entities
        mock_pipeline = MagicMock(return_value=fake_entities)
        with patch("pipeline.ner._load", return_value=mock_pipeline):
            from pipeline.ner import extract_entities
            result = extract_entities("text privind bugetul")

    assert result["extracted_date"] == "15 martie 2024"
    assert result["extracted_time"] == "10:00"
    assert result["extracted_place"] == "Cluj-Napoca"


def test_ner_subject_heuristic():
    with patch("pipeline.ner._load", return_value=MagicMock(return_value=[])):
        from pipeline.ner import extract_entities
        result = extract_entities("Consultare publică privind bugetul local pe 2024.")
    assert result["extracted_subject"] == "bugetul local pe 2024"


# ---------------------------------------------------------------------------
# Database — save_analysis / get_analysis
# ---------------------------------------------------------------------------


def _make_db() -> ArticleDB:
    return ArticleDB(db_path=":memory:")


def _insert_article(db: ArticleDB, url: str = "http://example.com/1") -> int:
    row_id = db.save_article(url=url, content="test content")
    assert row_id is not None
    return row_id


def _make_result(article_id: int, **kwargs) -> AnalysisResult:
    defaults = dict(
        article_id=article_id,
        keyword_matched=True,
        matched_keywords=["dezbatere publică"],
        is_public_consultation=True,
        classifier_score=0.72,
        extracted_date="2024-03-15",
        extracted_time="10:00",
        extracted_place="Cluj-Napoca",
        extracted_subject="bugetul local",
        processed_at=datetime.utcnow().isoformat(),
    )
    defaults.update(kwargs)
    return AnalysisResult(**defaults)


def test_db_save_and_get_analysis():
    db = _make_db()
    art_id = _insert_article(db)
    result = _make_result(art_id)

    row_id = db.save_analysis(result)
    assert row_id is not None

    retrieved = db.get_analysis(art_id)
    assert retrieved is not None
    assert retrieved.article_id == art_id
    assert retrieved.keyword_matched is True
    assert "dezbatere publică" in retrieved.matched_keywords
    assert retrieved.is_public_consultation is True
    assert retrieved.classifier_score == pytest.approx(0.72)
    assert retrieved.extracted_place == "Cluj-Napoca"


def test_db_get_analysis_missing():
    db = _make_db()
    assert db.get_analysis(999) is None


# ---------------------------------------------------------------------------
# Runner — list_unprocessed filtering
# ---------------------------------------------------------------------------


def test_runner_skips_already_processed():
    db = _make_db()
    id1 = _insert_article(db, "http://example.com/1")
    id2 = _insert_article(db, "http://example.com/2")

    # Mark id1 as processed
    db.save_analysis(_make_result(id1))

    unprocessed = db.list_unprocessed(limit=100)
    ids = [a.id for a in unprocessed]
    assert id1 not in ids
    assert id2 in ids


# ---------------------------------------------------------------------------
# Runner — end-to-end with mocked models
# ---------------------------------------------------------------------------


def test_runner_end_to_end():
    db = _make_db()
    art_id = _insert_article(db, "http://example.com/e2e")

    # Patch the article's content so keyword filter fires
    with db._conn() as conn:
        conn.execute(
            "UPDATE articles SET content = ? WHERE id = ?",
            ("Anunțăm o consultare publică privind bugetul.", art_id),
        )

    with patch("pipeline.runner.classify", return_value=(True, 0.80)), patch(
        "pipeline.runner.extract_entities",
        return_value={
            "extracted_date": None,
            "extracted_time": None,
            "extracted_place": None,
            "extracted_subject": "bugetul",
        },
    ):
        from pipeline.runner import run_pipeline
        summary = run_pipeline(db, batch_size=10, verbose=False)

    assert summary["processed"] == 1
    assert summary["matched"] == 1
    assert summary["classified_positive"] == 1

    analysis = db.get_analysis(art_id)
    assert analysis is not None
    assert analysis.is_public_consultation is True
    assert analysis.classifier_score == pytest.approx(0.80)


# ---------------------------------------------------------------------------
# Runner — use_keyword_filter flag
# ---------------------------------------------------------------------------


def test_runner_no_keyword_filter_classifies_without_keyword_match():
    """Articles that don't match any keyword should still be classified when the filter is disabled."""
    db = _make_db()
    art_id = _insert_article(db, "http://example.com/no-kw")

    with db._conn() as conn:
        conn.execute(
            "UPDATE articles SET content = ? WHERE id = ?",
            ("Știri locale despre infrastructură rutieră.", art_id),
        )

    with patch("pipeline.runner.classify", return_value=(False, 0.30)) as mock_cls, patch(
        "pipeline.runner.extract_entities",
        return_value={"extracted_date": None, "extracted_time": None,
                      "extracted_place": None, "extracted_subject": None},
    ):
        from pipeline.runner import run_pipeline
        summary = run_pipeline(db, batch_size=10, verbose=False, use_keyword_filter=False)

    mock_cls.assert_called_once()
    assert summary["processed"] == 1
    analysis = db.get_analysis(art_id)
    assert analysis is not None
    assert analysis.classifier_score == pytest.approx(0.30)


def test_runner_keyword_filter_enabled_skips_no_match():
    """Default behaviour: articles without keyword matches are saved without classification."""
    db = _make_db()
    art_id = _insert_article(db, "http://example.com/no-kw")

    with db._conn() as conn:
        conn.execute(
            "UPDATE articles SET content = ? WHERE id = ?",
            ("Știri locale despre infrastructură rutieră.", art_id),
        )

    with patch("pipeline.runner.classify") as mock_cls:
        from pipeline.runner import run_pipeline
        run_pipeline(db, batch_size=10, verbose=False, use_keyword_filter=True)

    mock_cls.assert_not_called()
    analysis = db.get_analysis(art_id)
    assert analysis is not None
    assert analysis.is_public_consultation is None
    assert analysis.classifier_score is None


def test_process_single_no_keyword_filter_classifies_all():
    """process_single with use_keyword_filter=False always runs the classifier."""
    db = _make_db()
    art_id = _insert_article(db, "http://example.com/single")

    with db._conn() as conn:
        conn.execute(
            "UPDATE articles SET content = ? WHERE id = ?",
            ("Știri fără cuvinte cheie relevante.", art_id),
        )

    article = db.get_article(art_id)
    with patch("pipeline.runner.classify", return_value=(True, 0.55)) as mock_cls, patch(
        "pipeline.runner.extract_entities",
        return_value={"extracted_date": None, "extracted_time": None,
                      "extracted_place": None, "extracted_subject": None},
    ):
        from pipeline.runner import process_single
        result = process_single(article, db, use_keyword_filter=False)

    mock_cls.assert_called_once()
    assert result.is_public_consultation is True
    assert result.classifier_score == pytest.approx(0.55)


def test_process_single_keyword_filter_enabled_skips_no_match():
    """process_single default behaviour: no classify call when keywords don't match."""
    db = _make_db()
    art_id = _insert_article(db, "http://example.com/single-kw")

    with db._conn() as conn:
        conn.execute(
            "UPDATE articles SET content = ? WHERE id = ?",
            ("Știri fără cuvinte cheie relevante.", art_id),
        )

    article = db.get_article(art_id)
    with patch("pipeline.runner.classify") as mock_cls:
        from pipeline.runner import process_single
        result = process_single(article, db, use_keyword_filter=True)

    mock_cls.assert_not_called()
    assert result.is_public_consultation is None
    assert result.classifier_score is None
