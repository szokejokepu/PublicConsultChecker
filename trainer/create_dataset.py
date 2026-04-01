"""Label articles via a local Ollama model to produce a fine-tuning dataset.

Output format
-------------
A JSONL file (one JSON object per line) at --output with the fields:

    article_id  int    — primary key from the articles table
    url         str    — source URL (for traceability)
    title       str    — article title
    text        str    — full article content (not truncated)
    label       int    — 0 = general press release, 1 = public consultation
    confidence  str    — "high" | "medium" | "low"  (self-reported by the model)
    reason      str    — one-sentence justification from the model
    raw_response str   — verbatim model output (useful for debugging)

This file can be fed directly into the fine-tuning script.  Filter on
``confidence != "low"`` before training to remove uncertain labels.

Usage examples
--------------
    # Label everything, resume if interrupted:
    python -m trainer.create_dataset

    # First 200 articles, custom model, loud output:
    python -m trainer.create_dataset --limit 200 --model phi3:mini

    # Start fresh (ignore previous output):
    python -m trainer.create_dataset --no-resume
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import click
import ollama

from scraper.database import ArticleDB

_DB_DEFAULT = str(Path(__file__).parent.parent / "articles.db")
_OUTPUT_DEFAULT = str(Path(__file__).parent / "data" / "labels.jsonl")

# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

_PROMPT = """\
You are a classifier for Romanian municipal announcements.

Decide whether the article below is a PUBLIC CONSULTATION ANNOUNCEMENT.

━━━ LABEL 1 — Public consultation announcement ━━━
ALL of the following must be true:
• The article INVITES citizens or stakeholders to take part in a formal
  consultation process that has NOT yet taken place.
• It announces a specific upcoming event: a public meeting, public hearing,
  or a period during which written feedback can be submitted.
• The consultation concerns a concrete draft: a local government decision
  (proiect de hotărâre), urban plan (PUG/PUZ/PUD), budget proposal, or
  other specific legislative/administrative draft.
• Typical markers: "consultare publică", "dezbatere publică",
  "audiere publică", "Legea 52/2003", a future date + time + venue.

━━━ LABEL 0 — General press release (anything else) ━━━
Examples of label-0 content:
• A report on a consultation or meeting that already happened.
• General municipal news: road works, cultural events, awards, appointments.
• An article that merely mentions "consultare" in passing without announcing
  an upcoming process open for citizen participation.
• Progress reports, infrastructure updates, or project completions.
• Invitations to events that are not formal public consultations (e.g.
  open-day visits, press conferences, public celebrations).

━━━ Response format ━━━
Reply with ONLY a single-line JSON object — no markdown, no extra text:
{{"label": <0 or 1>, "confidence": "<high|medium|low>", "reason": "<one sentence in English>"}}

Use "low" confidence when the article is ambiguous or the text is too short
to be certain.

━━━ Article ━━━
Title: {title}

{text}
"""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_done_ids(path: Path) -> set[int]:
    """Return the set of article IDs already written to *path*."""
    done: set[int] = set()
    if not path.exists():
        return done
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                done.add(json.loads(line)["article_id"])
            except (json.JSONDecodeError, KeyError):
                pass
    return done


def _parse_label(raw: str) -> dict | None:
    """Extract the JSON object from *raw*.  Returns None if parsing fails."""
    match = re.search(r'\{.*?}', raw, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group())
    except json.JSONDecodeError:
        return None
    if data.get("label") not in (0, 1):
        return None
    data.setdefault("confidence", "unknown")
    data.setdefault("reason", "")
    return data


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@click.command()
@click.option("--db", default=_DB_DEFAULT, show_default=True, metavar="PATH",
              help="Path to the SQLite articles database.")
@click.option("--output", default=_OUTPUT_DEFAULT, show_default=True, metavar="PATH",
              help="Destination JSONL file.")
@click.option("--model", default="llama3.1:8b", show_default=True,
              help="Ollama model name.")
@click.option("--limit", default=None, type=int, metavar="N",
              help="Stop after labeling N articles (default: all).")
@click.option("--max-chars", default=2000, show_default=True, metavar="N",
              help="Truncate article text to N characters before sending.")
@click.option("--no-resume", is_flag=True, default=False,
              help="Ignore existing output and re-label from scratch.")
@click.option("--quiet", "-q", is_flag=True,
              help="Suppress per-article output.")
def main(
    db: str,
    output: str,
    model: str,
    limit: int | None,
    max_chars: int,
    no_resume: bool,
    quiet: bool,
) -> None:
    """Label articles with a local Ollama model for BERT fine-tuning."""

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    article_db = ArticleDB(db_path=db)
    total_in_db = article_db.get_stats()["total_articles"]

    done_ids = set() if no_resume else _load_done_ids(output_path)
    if done_ids and not quiet:
        click.echo(f"Resuming — {len(done_ids)} article(s) already labeled, skipping.")

    fetch_limit = limit if limit is not None else total_in_db
    articles = article_db.list_articles(limit=fetch_limit, offset=0)
    pending = [a for a in articles if a.id not in done_ids]

    if not pending:
        click.echo("Nothing to label.")
        return

    click.echo(f"Model : {model}")
    click.echo(f"Output: {output_path}")
    click.echo(f"To label: {len(pending)} article(s)\n")

    labeled = skipped = failed = 0

    with output_path.open("a", encoding="utf-8") as out_fh:
        for i, article in enumerate(pending, 1):
            prefix = f"[{i}/{len(pending)}] #{article.id}"

            text = (article.content or "").strip()
            if not text:
                if not quiet:
                    click.echo(f"{prefix}: skip — no content")
                skipped += 1
                continue

            truncated = text[:max_chars] + ("…" if len(text) > max_chars else "")
            prompt = _PROMPT.format(
                title=article.title or "(no title)",
                text=truncated,
            )

            try:
                response = ollama.chat(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    options={"temperature": 0},
                )
                raw = response["message"]["content"].strip()
            except Exception as exc:
                click.echo(f"{prefix}: Ollama error — {exc}", err=True)
                failed += 1
                continue

            parsed = _parse_label(raw)
            if parsed is None:
                click.echo(f"{prefix}: could not parse response — {raw[:120]!r}", err=True)
                failed += 1
                continue

            record = {
                "article_id": article.id,
                "url": article.url,
                "title": article.title,
                "text": text,
                "label": parsed["label"],
                "confidence": parsed["confidence"],
                "reason": parsed["reason"],
                "raw_response": raw,
            }
            out_fh.write(json.dumps(record, ensure_ascii=False) + "\n")
            out_fh.flush()
            labeled += 1

            if not quiet:
                mark = click.style("✓", fg="green") if parsed["label"] == 1 else click.style("✗", fg="yellow")
                conf = parsed["confidence"]
                reason = parsed["reason"][:70]
                click.echo(f"{prefix} {mark}  [{conf}]  {reason}")

    click.echo(f"\nDone — labeled: {labeled}, skipped: {skipped}, failed: {failed}")
    click.echo(f"Output: {output_path.resolve()}")


if __name__ == "__main__":
    main()
