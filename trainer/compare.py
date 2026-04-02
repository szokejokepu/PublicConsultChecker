"""Compare Ollama baseline vs fine-tuned BERT on human-reviewed records.

Only records with ``"reviewed": true`` are used — those are the ones where a
human confirmed or corrected the label, so they are the ground truth.

For each reviewed record:
  - true label  = current ``label`` field (post-correction)
  - Ollama pred = ``original_label`` if the record was flipped, else ``label``
                  (i.e., what Ollama originally said)
  - BERT pred   = inference result from the fine-tuned model

Usage
-----
    python -m trainer.compare
    python -m trainer.compare --model-dir trainer/output/consultation_classifier
    python -m trainer.compare --input trainer/data/labels.jsonl
"""

from __future__ import annotations

import json
from pathlib import Path

import click

_INPUT_DEFAULT = str(Path(__file__).parent / "data" / "labels.jsonl")
_MODEL_DEFAULT = str(Path(__file__).parent / "output" / "consultation_classifier")
_MAX_CHARS = 4000


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


def _metrics(true: list[int], pred: list[int]) -> dict:
    from sklearn.metrics import (  # type: ignore
        accuracy_score, f1_score, precision_score, recall_score, confusion_matrix
    )
    return {
        "accuracy": accuracy_score(true, pred),
        "precision": precision_score(true, pred, zero_division=0),
        "recall": recall_score(true, pred, zero_division=0),
        "f1": f1_score(true, pred, zero_division=0),
        "confusion_matrix": confusion_matrix(true, pred).tolist(),
    }


def _print_metrics(name: str, m: dict) -> None:
    click.echo(f"\n{'─' * 40}")
    click.echo(click.style(f"  {name}", bold=True))
    click.echo(f"{'─' * 40}")
    click.echo(f"  Accuracy  : {m['accuracy']:.3f}")
    click.echo(f"  Precision : {m['precision']:.3f}")
    click.echo(f"  Recall    : {m['recall']:.3f}")
    click.echo(f"  F1        : {m['f1']:.3f}")
    tn, fp, fn, tp = (
        m["confusion_matrix"][0][0],
        m["confusion_matrix"][0][1],
        m["confusion_matrix"][1][0],
        m["confusion_matrix"][1][1],
    )
    click.echo(f"  Confusion : TP={tp}  FP={fp}  FN={fn}  TN={tn}")


@click.command()
@click.option("--input", "input_path", default=_INPUT_DEFAULT, show_default=True,
              metavar="PATH", help="JSONL labels file.")
@click.option("--model-dir", default=_MODEL_DEFAULT, show_default=True,
              metavar="PATH", help="Directory of the fine-tuned BERT model.")
@click.option("--batch-size", default=16, show_default=True, type=int,
              help="Batch size for BERT inference.")
def main(input_path: str, model_dir: str, batch_size: int) -> None:
    """Compare Ollama vs fine-tuned BERT against human-reviewed ground truth."""

    try:
        from transformers import pipeline  # type: ignore
        from sklearn.metrics import accuracy_score  # type: ignore  # noqa: F401
    except ImportError:
        raise click.ClickException(
            "Missing dependencies. Run:\n  pip install transformers torch scikit-learn"
        )

    path = Path(input_path)
    if not path.exists():
        raise click.ClickException(f"File not found: {path}")

    records = _load_reviewed(path)
    if not records:
        raise click.ClickException("No reviewed records found. Run review_dataset.py first.")

    flipped = sum(1 for r in records if "original_label" in r)
    click.echo(f"Reviewed records : {len(records)}")
    click.echo(f"Human-flipped    : {flipped}")

    true_labels = [r["label"] for r in records]
    ollama_preds = [_ollama_pred(r) for r in records]

    # ---- BERT inference ---------------------------------------------------
    model_path = Path(model_dir)
    if not model_path.exists():
        raise click.ClickException(
            f"Model not found at {model_path}. Run finetune.py first."
        )

    click.echo(f"\nLoading BERT model from {model_path}…")
    clf = pipeline(
        "text-classification",
        model=str(model_path),
        tokenizer=str(model_path),
        truncation=True,
        max_length=256,
        batch_size=batch_size,
        device=-1,  # CPU; set to 0 for GPU
    )

    click.echo("Running BERT inference…")
    texts = [_make_text(r) for r in records]
    results = clf(texts)

    label2id = {"PRESS_RELEASE": 0, "PUBLIC_CONSULTATION": 1}
    bert_preds = [label2id.get(r["label"], int(r["label"] == "LABEL_1")) for r in results]

    # ---- report -----------------------------------------------------------
    ollama_m = _metrics(true_labels, ollama_preds)
    bert_m = _metrics(true_labels, bert_preds)

    click.echo(f"\n{'═' * 40}")
    click.echo(click.style("  CLASSIFICATION COMPARISON", bold=True))
    click.echo(f"  Ground truth: {len(records)} human-reviewed articles")
    click.echo(f"{'═' * 40}")

    _print_metrics("Ollama (llama3.1:8b baseline)", ollama_m)
    _print_metrics("Fine-tuned BERT", bert_m)

    # ---- delta summary ----------------------------------------------------
    click.echo(f"\n{'─' * 40}")
    delta_acc = bert_m["accuracy"] - ollama_m["accuracy"]
    delta_f1 = bert_m["f1"] - ollama_m["f1"]
    acc_color = "green" if delta_acc >= 0 else "red"
    f1_color = "green" if delta_f1 >= 0 else "red"
    click.echo("  Delta (BERT − Ollama):")
    click.echo(f"  Accuracy : {click.style(f'{delta_acc:+.3f}', fg=acc_color)}")
    click.echo(f"  F1       : {click.style(f'{delta_f1:+.3f}', fg=f1_color)}")
    click.echo(f"{'─' * 40}\n")


if __name__ == "__main__":
    main()
