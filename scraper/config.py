"""Configuration DTO for the scrape command."""

from __future__ import annotations

from dataclasses import dataclass, field

from pipeline.classifier import DEFAULT_MODEL_NAME, DEFAULT_POSITIVE_REFS


DEFAULT_ARTICLE_LINK_SELECTOR = ".comunicate_presa_right h2 a"
DEFAULT_PAGES = 1
DEFAULT_WORKERS = 8

# Pagination URL format for pages > 1: base + PAGE_SEPARATOR + PAGE_PREFIX + N + PAGE_SUFFIX
# Default produces:  https://example.com/stiri-page2/
DEFAULT_PAGE_SEPARATOR = "-"
DEFAULT_PAGE_PREFIX = "page"
DEFAULT_PAGE_SUFFIX = "/"


@dataclass
class ScrapeConfig:
    url: str
    selector: str | None = DEFAULT_ARTICLE_LINK_SELECTOR
    max_pages: int | None = DEFAULT_PAGES
    workers: int | None = DEFAULT_WORKERS
    page_separator: str = DEFAULT_PAGE_SEPARATOR
    page_prefix: str = DEFAULT_PAGE_PREFIX
    page_suffix: str = DEFAULT_PAGE_SUFFIX
    model_name: str = DEFAULT_MODEL_NAME
    positive_refs: list[str] = field(default_factory=lambda: list(DEFAULT_POSITIVE_REFS))

    @classmethod
    def from_dict(cls, data: dict) -> ScrapeConfig:
        allowed = {f.name for f in cls.__dataclass_fields__.values()}
        unknown = set(data) - allowed
        if unknown:
            raise ValueError(f"Unknown config keys: {', '.join(sorted(unknown))}")
        return cls(
            url=data.get("url"),
            selector=data.get("selector"),
            max_pages=data.get("max_pages"),
            workers=data.get("workers"),
            page_separator=data.get("page_separator", DEFAULT_PAGE_SEPARATOR),
            page_prefix=data.get("page_prefix", DEFAULT_PAGE_PREFIX),
            page_suffix=data.get("page_suffix", DEFAULT_PAGE_SUFFIX),
            model_name=data.get("model_name", DEFAULT_MODEL_NAME),
            positive_refs=data.get("positive_refs", list(DEFAULT_POSITIVE_REFS)),
        )
