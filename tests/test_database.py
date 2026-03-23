"""Tests for scraper.database using an in-memory SQLite database."""

import pytest

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
