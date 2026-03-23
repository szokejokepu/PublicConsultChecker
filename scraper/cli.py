"""Command-line interface for the article scraper (Click)."""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import click

from .crawler import ARTICLE_LINK_SELECTOR, DEFAULT_WORKERS, crawl_paginated
from .database import Article, ArticleDB

_DB_DEFAULT = str(Path(__file__).parent.parent / "articles.db")
_SNIPPET_WIDTH = 120
_CONTENT_PREVIEW = 500


# ---------------------------------------------------------------------------
# Root group — carries --db across all subcommands via context
# ---------------------------------------------------------------------------


@click.group()
@click.option(
    "--db",
    default=_DB_DEFAULT,
    show_default=True,
    metavar="PATH",
    help="Path to the SQLite database file.",
)
@click.pass_context
def cli(ctx: click.Context, db: str) -> None:
    """Scrape web articles and query them via SQLite."""
    ctx.ensure_object(dict)
    ctx.obj["db"] = ArticleDB(db_path=db)


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------


@cli.command()
@click.argument("url")
@click.option("--selector", default=None, help="CSS selector for article links (overrides default).")
@click.option("--max-pages", default=None, type=int, help="Stop after this many listing pages (default: unlimited).")
@click.option("--workers", default=DEFAULT_WORKERS, show_default=True, type=int, help="Parallel article fetch threads.")
@click.option("--quiet", "-q", is_flag=True, help="Suppress per-article output.")
@click.pass_context
def scrape(ctx: click.Context, url: str, selector: str | None, max_pages: int | None, workers: int, quiet: bool) -> None:
    """Crawl a paginated listing at URL and save articles to the database."""
    db: ArticleDB = ctx.obj["db"]
    used_selector = selector or ARTICLE_LINK_SELECTOR
    click.echo(f"Crawling {url!r}  (selector={used_selector!r}, max_pages={max_pages or 'unlimited'}, workers={workers})")
    summary = crawl_paginated(url, db, selector=used_selector, max_pages=max_pages, max_workers=workers, verbose=not quiet)
    click.echo(
        f"\nDone — saved: {summary['saved']}, "
        f"skipped/duplicates: {summary['skipped']}, "
        f"failed: {summary['failed']}"
    )


@cli.command(name="list")
@click.option("--limit", default=50, show_default=True, help="Max rows to show.")
@click.option("--offset", default=0, show_default=True, help="Skip this many rows.")
@click.pass_context
def list_cmd(ctx: click.Context, limit: int, offset: int) -> None:
    """List saved articles."""
    db: ArticleDB = ctx.obj["db"]
    articles = db.list_articles(limit=limit, offset=offset)
    if not articles:
        click.echo("No articles found.")
        return
    _print_table(articles)


@cli.command()
@click.argument("id", type=int)
@click.option("--full", is_flag=True, help="Print entire content.")
@click.pass_context
def show(ctx: click.Context, id: int, full: bool) -> None:
    """Show a single article by ID."""
    db: ArticleDB = ctx.obj["db"]
    article = db.get_article(id)
    if article is None:
        click.echo(f"No article with id={id}.", err=True)
        sys.exit(1)
    _print_article(article, full=full)


@cli.command()
@click.argument("query", nargs=-1, required=True)
@click.option("--limit", default=20, show_default=True, help="Max results.")
@click.pass_context
def search(ctx: click.Context, query: tuple[str, ...], limit: int) -> None:
    """Full-text search across articles."""
    db: ArticleDB = ctx.obj["db"]
    articles = db.search_articles(" ".join(query), limit=limit)
    if not articles:
        click.echo("No results.")
        return
    _print_table(articles)


@cli.command()
@click.argument("id", type=int)
@click.pass_context
def delete(ctx: click.Context, id: int) -> None:
    """Delete an article by ID."""
    db: ArticleDB = ctx.obj["db"]
    if db.delete_article(id):
        click.echo(f"Deleted article #{id}.")
    else:
        click.echo(f"No article with id={id}.", err=True)
        sys.exit(1)


@cli.command()
@click.pass_context
def stats(ctx: click.Context) -> None:
    """Show database statistics."""
    db: ArticleDB = ctx.obj["db"]
    s = db.get_stats()
    click.echo(f"Total articles  : {s['total_articles']}")
    click.echo(f"Unique sources  : {s['unique_sources']}")
    click.echo(f"Last scraped at : {s['newest_scraped_at'] or 'n/a'}")


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------


def _print_table(articles: list[Article]) -> None:
    click.echo(f"{'ID':>5}  {'Date':<12}  {'Author':<20}  Title")
    click.echo("-" * 80)
    for a in articles:
        title = (a.title or a.url)[:50]
        author = (a.author or "")[:20]
        date = (a.date or "")[:10]
        click.echo(f"{a.id:>5}  {date:<12}  {author:<20}  {title}")


def _print_article(article: Article, *, full: bool = False) -> None:
    click.echo(f"ID      : {article.id}")
    click.echo(f"URL     : {article.url}")
    click.echo(f"Title   : {article.title or '(none)'}")
    click.echo(f"Author  : {article.author or '(none)'}")
    click.echo(f"Date    : {article.date or '(none)'}")
    click.echo(f"Scraped : {article.scraped_at}")
    click.echo(f"Source  : {article.source_url or '(none)'}")
    click.echo()
    content = article.content or ""
    if not full and len(content) > _CONTENT_PREVIEW:
        content = content[:_CONTENT_PREVIEW] + "\n… (use --full to see everything)"
    click.echo(textwrap.fill(content, width=_SNIPPET_WIDTH))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    cli()


if __name__ == "__main__":
    main()