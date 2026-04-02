"""Compare four classifiers on human-reviewed ground-truth records.

Only records with ``"reviewed": true`` are used as ground truth.

Methods compared
----------------
1. Keyword filter        — exact string match on Romanian consultation keywords
2. Cosine similarity     — mean cosine score against positive reference sentences
                           using the base Romanian BERT (no fine-tuning)
3. Ollama (LLM baseline) — what the LLM originally predicted before human review
4. Fine-tuned BERT       — the model produced by finetune.py

Usage
-----
    python -m trainer.compare
    python -m trainer.compare --model-dir trainer/output/consultation_classifier
    python -m trainer.compare --cosine-threshold 0.65
    python -m trainer.compare --skip-cosine   # faster, skips the slow embedding pass
"""

from __future__ import annotations

import json
from pathlib import Path

import click

_INPUT_DEFAULT = str(Path(__file__).parent / "data" / "labels.jsonl")
_MODEL_DEFAULT = str(Path(__file__).parent / "output" / "consultation_classifier")
_MAX_CHARS = 4000


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------


def _load_reviewed(path: Path) -> list[dict]:
    records = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("reviewed"):
                records.append(r)
    return records


def _ollama_pred(record: dict) -> int:
    """What Ollama originally predicted (before any human flip)."""
    return record.get("original_label", record["label"])


def _make_text(record: dict) -> str:
    title = (record.get("title") or "").strip()
    body = (record.get("text") or "").strip()
    combined = f"{title}\n\n{body}" if title else body
    return combined[:_MAX_CHARS]


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


def _metrics(true: list[int], pred: list[int]) -> dict:
    from sklearn.metrics import (  # type: ignore
        accuracy_score, f1_score, precision_score, recall_score, confusion_matrix,
    )
    return {
        "accuracy": accuracy_score(true, pred),
        "precision": precision_score(true, pred, zero_division=0),
        "recall": recall_score(true, pred, zero_division=0),
        "f1": f1_score(true, pred, zero_division=0),
        "confusion_matrix": confusion_matrix(true, pred).tolist(),
    }


def _print_metrics(name: str, m: dict) -> None:
    click.echo(f"\n{'─' * 44}")
    click.echo(click.style(f"  {name}", bold=True))
    click.echo(f"{'─' * 44}")
    click.echo(f"  Accuracy  : {m['accuracy']:.3f}")
    click.echo(f"  Precision : {m['precision']:.3f}")
    click.echo(f"  Recall    : {m['recall']:.3f}")
    click.echo(f"  F1        : {m['f1']:.3f}")
    tn = m["confusion_matrix"][0][0]
    fp = m["confusion_matrix"][0][1]
    fn = m["confusion_matrix"][1][0]
    tp = m["confusion_matrix"][1][1]
    click.echo(f"  Confusion : TP={tp}  FP={fp}  FN={fn}  TN={tn}")


def _delta_line(label: str, val: float) -> None:
    color = "green" if val >= 0 else "red"
    click.echo(f"  {label:<12}: {click.style(f'{val:+.3f}', fg=color)}")


# ---------------------------------------------------------------------------
# Classifiers
# ---------------------------------------------------------------------------


def _keyword_preds(records: list[dict]) -> list[int]:
    from pipeline.keyword_filter import keyword_filter  # type: ignore
    preds = []
    for r in records:
        text = _make_text(r).lower()
        matched, _ = keyword_filter(text)
        preds.append(1 if matched else 0)
    return preds


def _cosine_preds(records: list[dict], threshold: float) -> list[int]:
    from pipeline.classifier import classify  # type: ignore
    preds = []
    total = len(records)
    for i, r in enumerate(records, 1):
        text = _make_text(r)
        is_pos, _ = classify(text, threshold=threshold)
        preds.append(1 if is_pos else 0)
        if i % 10 == 0 or i == total:
            click.echo(f"  cosine: {i}/{total}", nl=False)
            click.echo("\r", nl=False)
    click.echo(" " * 30 + "\r", nl=False)  # clear line
    return preds


def _bert_preds(records: list[dict], model_path: Path, batch_size: int) -> list[int]:
    from transformers import pipeline  # type: ignore
    clf = pipeline(
        "text-classification",
        model=str(model_path),
        tokenizer=str(model_path),
        truncation=True,
        max_length=256,
        batch_size=batch_size,
        device=-1,
    )
    texts = [_make_text(r) for r in records]
    results = clf(texts)
    label2id = {"PRESS_RELEASE": 0, "PUBLIC_CONSULTATION": 1}
    return [label2id.get(r["label"], int(r["label"] == "LABEL_1")) for r in results]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@click.command()
@click.option("--input", "input_path", default=_INPUT_DEFAULT, show_default=True,
              metavar="PATH", help="JSONL labels file.")
@click.option("--model-dir", default=_MODEL_DEFAULT, show_default=True,
              metavar="PATH", help="Directory of the fine-tuned BERT model.")
@click.option("--batch-size", default=16, show_default=True, type=int,
              help="Batch size for fine-tuned BERT inference.")
@click.option("--cosine-threshold", default=0.65, show_default=True, type=float,
              help="Decision threshold for the cosine similarity classifier.")
@click.option("--skip-cosine", is_flag=True, default=False,
              help="Skip the cosine similarity step (slow on CPU for large sets).")
@click.option("--skip-bert", is_flag=True, default=False,
              help="Skip the fine-tuned BERT step.")
def main(
    input_path: str,
    model_dir: str,
    batch_size: int,
    cosine_threshold: float,
    skip_cosine: bool,
    skip_bert: bool,
) -> None:
    """Compare keyword / cosine / Ollama / fine-tuned BERT classifiers."""

    try:
        from sklearn.metrics import accuracy_score  # type: ignore  # noqa: F401
    except ImportError:
        raise click.ClickException("Run: pip install scikit-learn")

    path = Path(input_path)
    if not path.exists():
        raise click.ClickException(f"File not found: {path}")

    records = _load_reviewed(path)
    if not records:
        raise click.ClickException("No reviewed records found. Run review_dataset.py first.")

    flipped = sum(1 for r in records if "original_label" in r)
    pos = sum(1 for r in records if r["label"] == 1)
    click.echo(f"Reviewed records : {len(records)}  (label=1: {pos}, label=0: {len(records)-pos})")
    click.echo(f"Human-flipped    : {flipped}")

    true_labels = [r["label"] for r in records]

    # ---- keyword -----------------------------------------------------------
    click.echo("\nRunning keyword filter…")
    kw_preds = _keyword_preds(records)

    # ---- cosine ------------------------------------------------------------
    if not skip_cosine:
        click.echo(f"Running cosine similarity (threshold={cosine_threshold})…")
        cosine_preds = _cosine_preds(records, cosine_threshold)
    else:
        cosine_preds = None

    # ---- Ollama ------------------------------------------------------------
    ollama_preds = [_ollama_pred(r) for r in records]

    # ---- fine-tuned BERT ---------------------------------------------------
    if not skip_bert:
        model_path = Path(model_dir)
        if not model_path.exists():
            raise click.ClickException(
                f"Fine-tuned model not found at {model_path}. "
                "Run finetune.py first, or use --skip-bert."
            )
        click.echo(f"Running fine-tuned BERT from {model_path}…")
        bert_preds = _bert_preds(records, model_path, batch_size)
    else:
        bert_preds = None

    # ---- report ------------------------------------------------------------
    kw_m = _metrics(true_labels, kw_preds)
    cosine_m = _metrics(true_labels, cosine_preds) if cosine_preds is not None else None
    ollama_m = _metrics(true_labels, ollama_preds)
    bert_m = _metrics(true_labels, bert_preds) if bert_preds is not None else None

    click.echo(f"\n{'═' * 44}")
    click.echo(click.style("  CLASSIFICATION COMPARISON", bold=True))
    click.echo(f"  Ground truth: {len(records)} human-reviewed articles")
    click.echo(f"{'═' * 44}")

    _print_metrics("1. Keyword filter", kw_m)
    if cosine_m:
        _print_metrics(f"2. Cosine similarity (≥{cosine_threshold})", cosine_m)
    _print_metrics("3. Ollama (llama3.1:8b)", ollama_m)
    if bert_m:
        _print_metrics("4. Fine-tuned BERT", bert_m)

    # ---- delta vs Ollama --------------------------------------------------
    click.echo(f"\n{'─' * 44}")
    click.echo(click.style("  Delta vs Ollama (F1 / Accuracy)", bold=True))
    click.echo(f"{'─' * 44}")
    _delta_line("Keyword", kw_m["f1"] - ollama_m["f1"])
    if cosine_m:
        _delta_line("Cosine", cosine_m["f1"] - ollama_m["f1"])
    if bert_m:
        _delta_line("Fine-tuned", bert_m["f1"] - ollama_m["f1"])
    click.echo(f"{'─' * 44}\n")


if __name__ == "__main__":
    main()
