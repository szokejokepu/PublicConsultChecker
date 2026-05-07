"""Storage backend interface and shared data types."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pipeline.models import AnalysisResult


@dataclass
class Article:
    id: int | None
    url: str
    title: str | None
    author: str | None
    date: str | None
    content: str | None
    source_url: str | None
    scraped_at: str
    starred: bool = False


@dataclass
class SchedulerSettings:
    enabled: bool
    interval_minutes: int
    use_keyword_filter: bool
    batch_size: int
    reprocess_all: bool
    notify_always: bool = False


@dataclass
class CrawlSession:
    id: int
    triggered_at: str
    trigger_source: str
    config_url: str
    status: str
    finished_at: str | None
    saved: int | None
    skipped: int | None
    failed: int | None
    error: str | None


class StorageBackend(ABC):
    """Abstract interface all storage backends must implement."""

    @abstractmethod
    def close(self) -> None: ...

    @abstractmethod
    def save_article(
        self,
        *,
        url: str,
        title: str | None = None,
        author: str | None = None,
        date: str | None = None,
        content: str | None = None,
        source_url: str | None = None,
    ) -> int | None: ...

    @abstractmethod
    def set_starred(self, article_id: int, starred: bool) -> bool: ...

    @abstractmethod
    def delete_article(self, article_id: int) -> bool: ...

    @abstractmethod
    def url_exists(self, url: str) -> bool: ...

    @abstractmethod
    def get_article(self, article_id: int) -> Article | None: ...

    @abstractmethod
    def list_articles(
        self,
        limit: int = 50,
        offset: int = 0,
        sort_by: str = "scraped_at",
        sort_order: str = "desc",
    ) -> list[Article]: ...

    @abstractmethod
    def search_articles(self, query: str, limit: int = 20) -> list[Article]: ...

    @abstractmethod
    def get_stats(self) -> dict: ...

    @abstractmethod
    def save_analysis(self, result: "AnalysisResult") -> int | None: ...

    @abstractmethod
    def get_analysis(self, article_id: int) -> "AnalysisResult | None": ...

    @abstractmethod
    def filter_articles(
        self,
        limit: int = 50,
        offset: int = 0,
        processed: str = "any",
        consultation: str = "any",
        min_score: float | None = None,
        starred: str = "any",
        sort_by: str = "scraped_at",
        sort_order: str = "desc",
    ) -> tuple[list[Article], int]: ...

    @abstractmethod
    def create_crawl_session(
        self,
        *,
        triggered_at: str,
        trigger_source: str,
        config_url: str,
    ) -> int: ...

    @abstractmethod
    def finish_crawl_session(self, session_id: int, summary: dict) -> None: ...

    @abstractmethod
    def fail_crawl_session(self, session_id: int, error: str) -> None: ...

    @abstractmethod
    def link_articles_to_session(self, session_id: int, article_ids: list[int]) -> None: ...

    @abstractmethod
    def list_crawl_sessions(self, limit: int = 50, offset: int = 0) -> list[CrawlSession]: ...

    @abstractmethod
    def get_crawl_session_article_ids(self, session_id: int) -> list[int]: ...

    @abstractmethod
    def get_scheduler_settings(self) -> SchedulerSettings: ...

    @abstractmethod
    def save_scheduler_settings(self, s: SchedulerSettings) -> None: ...

    @abstractmethod
    def set_notified(self, article_id: int, notified_at: str) -> bool: ...

    @abstractmethod
    def list_unnotified_consultations(self) -> list[Article]: ...

    @abstractmethod
    def list_unprocessed(self, limit: int = 32) -> list[Article]: ...
