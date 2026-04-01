"""Interactive review tool for Ollama-labeled articles.

Presents each article one at a time and lets you confirm or flip the label
with a single keypress.  Changes are written back to the JSONL file on exit.

Reviewed records gain a ``"reviewed": true`` field.  Flipped records also
gain an ``"original_label"`` field preserving what the model originally
assigned.

Usage examples
--------------
    # Review up to 20 unreviewed articles:
    python -m trainer.review_dataset --limit 20

    # Review only low-confidence labels:
    python -m trainer.review_dataset --confidence low

    # Re-review already confirmed articles:
    python -m trainer.review_dataset --all

Keybindings
-----------
    y / Enter   — keep label as-is and mark reviewed
    n           — flip label (0↔1) and mark reviewed
    r           — toggle full article text
    s           — skip (leave unreviewed)
    q           — save and quit
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import click

_INPUT_DEFAULT = str(Path(__file__).parent / "data" / "labels.jsonl")
_LABEL_NAMES = {0: "PRESS RELEASE", 1: "PUBLIC CONSULTATION"}
_CONF_ORDER = {"low": 0, "medium": 1, "high": 2, "unknown": 3}
_WIDTH = 72


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------


def _load(path: Path) -> list[dict]:
    records = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return records


def _save(path: Path, records: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------


def _rule(char: str = "─") -> str:
    return char * _WIDTH


def _wrap(text: str, indent: int = 0) -> str:
    prefix = " " * indent
    return textwrap.fill(text, width=_WIDTH - indent, initial_indent=prefix,
                         subsequent_indent=prefix)


def _extract_body(text: str, title: str | None) -> str:
    """Strip the navigation menu that precedes the article body."""
    if title:
        pos = text.find(title)
        if pos != -1:
            return text[pos:].strip()
    # Fallback: skip obvious nav lines (starting with "- ")
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line and not line.startswith("- "):
            return "\n".join(lines[i:]).strip()
    return text.strip()


def _render(record: dict, show_full: bool, index: int, total: int) -> None:
    click.clear()

    label = record["label"]
    conf = record.get("confidence", "unknown")
    reason = record.get("reason", "")
    title = record.get("title") or "(no title)"
    reviewed = record.get("reviewed", False)

    label_color = "green" if label == 1 else "yellow"
    label_str = click.style(f"{'✓' if label == 1 else '✗'}  {_LABEL_NAMES[label]} ({label})",
                             fg=label_color, bold=True)
    conf_color = {"high": "green", "medium": "yellow", "low": "red"}.get(conf, "white")
    conf_str = click.style(f"[{conf}]", fg=conf_color)

    reviewed_str = click.style(" ✔ reviewed", fg="cyan") if reviewed else ""

    click.echo(_rule("═"))
    click.echo(f"  Article {index}/{total}   #{record['article_id']}{reviewed_str}")
    click.echo(_rule())
    click.echo(_wrap(f"Title      {title}", indent=2))
    click.echo(f"  Label      {label_str}  {conf_str}")
    click.echo(_wrap(f"Reason     {reason}", indent=2))
    click.echo(_rule())

    body = _extract_body(record.get("text", ""), record.get("title"))
    if show_full:
        click.echo(_wrap(body, indent=2))
    else:
        preview = body[:600]
        click.echo(_wrap(preview, indent=2))
        if len(body) > 600:
            click.echo(click.style(f"\n  … {len(body) - 600} chars more", fg="bright_black"))

    click.echo(_rule("═"))
    click.echo(
        "  "
        + click.style("[y]", bold=True) + " keep  "
        + click.style("[n]", bold=True) + " flip  "
        + click.style("[r]", bold=True) + " read full  "
        + click.style("[s]", bold=True) + " skip  "
        + click.style("[q]", bold=True) + " save & quit"
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@click.command()
@click.option("--input", "input_path", default=_INPUT_DEFAULT, show_default=True,
              metavar="PATH", help="JSONL file produced by create_dataset.py.")
@click.option("--limit", default=None, type=int, metavar="N",
              help="Stop after reviewing N articles.")
@click.option("--confidence", "conf_filter", default=None,
              type=click.Choice(["low", "medium", "high"]),
              help="Only review articles with this confidence level.")
@click.option("--all", "include_reviewed", is_flag=True, default=False,
              help="Include already-reviewed articles.")
def main(input_path: str, limit: int | None, conf_filter: str | None,
         include_reviewed: bool) -> None:
    """Interactively review and correct article labels."""

    path = Path(input_path)
    if not path.exists():
        raise click.ClickException(f"File not found: {path}")

    all_records = _load(path)
    # Build an index so we can update records by article_id
    by_id: dict[int, dict] = {r["article_id"]: r for r in all_records}

    # Filter to reviewable candidates
    candidates = [
        r for r in all_records
        if (include_reviewed or not r.get("reviewed", False))
        and (conf_filter is None or r.get("confidence") == conf_filter)
    ]
    # Prioritise low confidence first
    candidates.sort(key=lambda r: _CONF_ORDER.get(r.get("confidence", "unknown"), 3))

    if limit is not None:
        candidates = candidates[:limit]

    if not candidates:
        click.echo("No articles to review.")
        return

    click.echo(f"Loaded {len(all_records)} records — {len(candidates)} to review.")
    click.echo("Press any key to start…")
    click.getchar()

    confirmed = flipped = skipped = 0
    show_full = False

    for i, record in enumerate(candidates, 1):
        show_full = False
        while True:
            _render(record, show_full, i, len(candidates))
            key = click.getchar().lower()

            if key in ("y", "\r", "\n"):
                by_id[record["article_id"]]["reviewed"] = True
                confirmed += 1
                break

            elif key == "n":
                orig = record["label"]
                by_id[record["article_id"]]["original_label"] = orig
                by_id[record["article_id"]]["label"] = 1 - orig
                by_id[record["article_id"]]["reviewed"] = True
                flipped += 1
                break

            elif key == "r":
                show_full = not show_full
                continue

            elif key == "s":
                skipped += 1
                break

            elif key == "q":
                _save(path, list(by_id.values()))
                click.clear()
                click.echo(f"Saved.  confirmed={confirmed}  flipped={flipped}  skipped={skipped}")
                return

    _save(path, list(by_id.values()))
    click.clear()
    click.echo(f"All done.  confirmed={confirmed}  flipped={flipped}  skipped={skipped}")
    click.echo(f"Saved to {path.resolve()}")


if __name__ == "__main__":
    main()
