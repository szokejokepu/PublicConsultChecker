"""Configuration DTO for the scrape command."""

from __future__ import annotations

from dataclasses import dataclass


DEFAULT_ARTICLE_LINK_SELECTOR = ".comunicate_presa_right h2 a"
DEFAULT_PAGES = 1
DEFAULT_WORKERS = 8


@dataclass
class ScrapeConfig:
    url: str
    selector: str | None =  DEFAULT_ARTICLE_LINK_SELECTOR
    max_pages: int | None = DEFAULT_PAGES
    workers: int | None = DEFAULT_WORKERS

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
        )
