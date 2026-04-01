"""Tests for scraper.database using an in-memory SQLite database."""

from datetime import datetime

import pytest

from pipeline.models import AnalysisResult
from scraper.database import ArticleDB


@pytest.fixture
def db():
    return ArticleDB(db_path=":memory:")


def _save(db: ArticleDB, **kwargs) -> int:
    defaults = dict(
        url="https://example.com/article",
        title="Test Article",
        author="Alice",
        date="2024-01-01",
        content="This is the article content. " * 10,
        source_url="https://example.com",
    )
    defaults.update(kwargs)
    return db.save_article(**defaults)


class TestSaveArticle:
    def test_returns_row_id(self, db):
        row_id = _save(db)
        assert isinstance(row_id, int)
        assert row_id > 0

    def test_duplicate_url_returns_none(self, db):
        _save(db, url="https://example.com/same")
        second = _save(db, url="https://example.com/same")
        assert second is None

    def test_different_urls_both_saved(self, db):
        id1 = _save(db, url="https://example.com/a")
        id2 = _save(db, url="https://example.com/b")
        assert id1 != id2
        assert db.get_stats()["total_articles"] == 2


class TestGetArticle:
    def test_retrieves_saved_article(self, db):
        row_id = _save(db, title="Hello World", author="Bob")
        article = db.get_article(row_id)
        assert article is not None
        assert article.title == "Hello World"
        assert article.author == "Bob"

    def test_unknown_id_returns_none(self, db):
        assert db.get_article(9999) is None


class TestUrlExists:
    def test_returns_false_for_unknown_url(self, db):
        assert db.url_exists("https://example.com/missing") is False

    def test_returns_true_after_save(self, db):
        _save(db, url="https://example.com/article")
        assert db.url_exists("https://example.com/article") is True

    def test_different_url_not_found(self, db):
        _save(db, url="https://example.com/a")
        assert db.url_exists("https://example.com/b") is False


class TestListArticles:
    def test_empty_db(self, db):
        assert db.list_articles() == []

    def test_returns_all(self, db):
        for i in range(5):
            _save(db, url=f"https://example.com/{i}")
        assert len(db.list_articles()) == 5

    def test_limit_and_offset(self, db):
        for i in range(10):
            _save(db, url=f"https://example.com/{i}")
        page1 = db.list_articles(limit=3, offset=0)
        page2 = db.list_articles(limit=3, offset=3)
        assert len(page1) == 3
        assert len(page2) == 3
        assert {a.id for a in page1}.isdisjoint({a.id for a in page2})


class TestSearchArticles:
    def test_finds_by_title_word(self, db):
        _save(db, url="https://a.com/1", title="Python programming tips", content="x " * 50)
        _save(db, url="https://a.com/2", title="Cooking recipes", content="y " * 50)
        results = db.search_articles("Python")
        assert len(results) == 1
        assert results[0].title == "Python programming tips"

    def test_no_results(self, db):
        _save(db)
        assert db.search_articles("nonexistentterm12345") == []


class TestDeleteArticle:
    def test_deletes_existing(self, db):
        row_id = _save(db)
        assert db.delete_article(row_id) is True
        assert db.get_article(row_id) is None

    def test_delete_nonexistent_returns_false(self, db):
        assert db.delete_article(9999) is False


def _make_analysis(article_id: int, *, is_public_consultation=True, score=0.80, keyword_matched=True) -> AnalysisResult:
    return AnalysisResult(
        article_id=article_id,
        keyword_matched=keyword_matched,
        matched_keywords=["consultare publică"] if keyword_matched else [],
        is_public_consultation=is_public_consultation,
        classifier_score=score if keyword_matched else None,
        extracted_date=None,
        extracted_time=None,
        extracted_place=None,
        extracted_subject=None,
        processed_at=datetime.utcnow().isoformat(),
    )


class TestSetStarred:
    def test_defaults_to_unstarred(self, db):
        row_id = _save(db)
        assert db.get_article(row_id).starred is False

    def test_set_starred_true(self, db):
        row_id = _save(db)
        db.set_starred(row_id, True)
        assert db.get_article(row_id).starred is True

    def test_set_starred_false_after_true(self, db):
        row_id = _save(db)
        db.set_starred(row_id, True)
        db.set_starred(row_id, False)
        assert db.get_article(row_id).starred is False

    def test_returns_false_for_unknown_id(self, db):
        assert db.set_starred(9999, True) is False

    def test_does_not_affect_other_articles(self, db):
        id1 = _save(db, url="https://example.com/a")
        id2 = _save(db, url="https://example.com/b")
        db.set_starred(id1, True)
        assert db.get_article(id2).starred is False


class TestFilterArticles:
    def test_no_filters_returns_all(self, db):
        for i in range(3):
            _save(db, url=f"https://example.com/{i}")
        articles, total = db.filter_articles(limit=50)
        assert len(articles) == 3
        assert total == 3

    def test_returns_correct_total(self, db):
        for i in range(5):
            _save(db, url=f"https://example.com/{i}")
        articles, total = db.filter_articles(limit=2)
        assert len(articles) == 2
        assert total == 5

    def test_filter_processed_yes(self, db):
        id1 = _save(db, url="https://example.com/a")
        _save(db, url="https://example.com/b")
        db.save_analysis(_make_analysis(id1))
        articles, total = db.filter_articles(processed="yes")
        assert total == 1
        assert articles[0].id == id1

    def test_filter_processed_no(self, db):
        id1 = _save(db, url="https://example.com/a")
        id2 = _save(db, url="https://example.com/b")
        db.save_analysis(_make_analysis(id1))
        articles, total = db.filter_articles(processed="no")
        assert total == 1
        assert articles[0].id == id2

    def test_filter_consultation_yes(self, db):
        id1 = _save(db, url="https://example.com/a")
        id2 = _save(db, url="https://example.com/b")
        db.save_analysis(_make_analysis(id1, is_public_consultation=True))
        db.save_analysis(_make_analysis(id2, is_public_consultation=False))
        articles, total = db.filter_articles(consultation="yes")
        assert total == 1
        assert articles[0].id == id1

    def test_filter_consultation_no(self, db):
        id1 = _save(db, url="https://example.com/a")
        id2 = _save(db, url="https://example.com/b")
        db.save_analysis(_make_analysis(id1, is_public_consultation=True))
        db.save_analysis(_make_analysis(id2, is_public_consultation=False))
        articles, total = db.filter_articles(consultation="no")
        assert total == 1
        assert articles[0].id == id2

    def test_filter_consultation_unclassified(self, db):
        id1 = _save(db, url="https://example.com/a")
        id2 = _save(db, url="https://example.com/b")
        db.save_analysis(_make_analysis(id1, is_public_consultation=None, keyword_matched=False))
        db.save_analysis(_make_analysis(id2, is_public_consultation=True))
        articles, total = db.filter_articles(consultation="unclassified")
        assert total == 1
        assert articles[0].id == id1

    def test_filter_min_score(self, db):
        id1 = _save(db, url="https://example.com/a")
        id2 = _save(db, url="https://example.com/b")
        db.save_analysis(_make_analysis(id1, score=0.90))
        db.save_analysis(_make_analysis(id2, score=0.50))
        articles, total = db.filter_articles(min_score=0.70)
        assert total == 1
        assert articles[0].id == id1

    def test_filter_starred_yes(self, db):
        id1 = _save(db, url="https://example.com/a")
        id2 = _save(db, url="https://example.com/b")
        db.set_starred(id1, True)
        articles, total = db.filter_articles(starred="yes")
        assert total == 1
        assert articles[0].id == id1

    def test_filter_starred_no(self, db):
        id1 = _save(db, url="https://example.com/a")
        id2 = _save(db, url="https://example.com/b")
        db.set_starred(id1, True)
        articles, total = db.filter_articles(starred="no")
        assert total == 1
        assert articles[0].id == id2

    def test_filters_combine(self, db):
        id1 = _save(db, url="https://example.com/a")
        id2 = _save(db, url="https://example.com/b")
        db.save_analysis(_make_analysis(id1, is_public_consultation=True))
        db.save_analysis(_make_analysis(id2, is_public_consultation=True))
        db.set_starred(id1, True)
        articles, total = db.filter_articles(consultation="yes", starred="yes")
        assert total == 1
        assert articles[0].id == id1


class TestGetStats:
    def test_empty(self, db):
        stats = db.get_stats()
        assert stats["total_articles"] == 0
        assert stats["unique_sources"] == 0
        assert stats["newest_scraped_at"] is None

    def test_counts(self, db):
        _save(db, url="https://a.com/1", source_url="https://a.com")
        _save(db, url="https://b.com/1", source_url="https://b.com")
        stats = db.get_stats()
        assert stats["total_articles"] == 2
        assert stats["unique_sources"] == 2
