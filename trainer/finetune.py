"""Fine-tune a Romanian BERT model on the labeled article dataset.

Reads the JSONL file produced by create_dataset.py (and optionally curated by
review_dataset.py) and fine-tunes a sequence classification model to distinguish
between public consultation announcements (label 1) and general press releases
(label 0).

The fine-tuned model is saved to --output-dir and can be loaded directly with
the HuggingFace ``transformers`` library for inference.

Usage examples
--------------
    # Basic fine-tune with defaults:
    python -m trainer.finetune

    # Only use human-reviewed records, train for 5 epochs:
    python -m trainer.finetune --only-reviewed --epochs 5

    # Custom model, skip low-confidence, save elsewhere:
    python -m trainer.finetune --model bert-base-multilingual-cased \\
        --min-confidence medium --output-dir models/my_classifier

Dependencies
------------
    pip install transformers torch scikit-learn
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Optional

import click

_INPUT_DEFAULT = str(Path(__file__).parent / "data" / "labels.jsonl")
_OUTPUT_DEFAULT = str(Path(__file__).parent / "output" / "consultation_classifier")
_DEFAULT_MODEL = "dumitrescustefan/bert-base-romanian-cased-v1"

_CONF_RANK = {"high": 3, "medium": 2, "low": 1, "unknown": 0}


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def _load_records(
    path: Path,
    only_reviewed: bool,
    min_confidence: Optional[str],
) -> list[dict]:
    """Load and filter records from the JSONL file."""
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

            if only_reviewed and not r.get("reviewed", False):
                continue

            if min_confidence is not None:
                conf_rank = _CONF_RANK.get(r.get("confidence", "unknown"), 0)
                if conf_rank < _CONF_RANK[min_confidence]:
                    continue

            if r.get("label") not in (0, 1):
                continue

            records.append(r)

    return records


def _split(records: list[dict], val_ratio: float, seed: int) -> tuple[list[dict], list[dict]]:
    """Stratified train/val split."""
    pos = [r for r in records if r["label"] == 1]
    neg = [r for r in records if r["label"] == 0]

    rng = random.Random(seed)
    rng.shuffle(pos)
    rng.shuffle(neg)

    def cut(lst: list) -> tuple[list, list]:
        n_val = max(1, int(len(lst) * val_ratio))
        return lst[n_val:], lst[:n_val]

    pos_train, pos_val = cut(pos)
    neg_train, neg_val = cut(neg)

    train = pos_train + neg_train
    val = pos_val + neg_val
    rng.shuffle(train)
    rng.shuffle(val)
    return train, val


def _make_text(record: dict, max_chars: int) -> str:
    """Combine title and text into a single string for the model."""
    title = (record.get("title") or "").strip()
    body = (record.get("text") or "").strip()
    combined = f"{title}\n\n{body}" if title else body
    return combined[:max_chars]


# ---------------------------------------------------------------------------
# Dataset
# ---------------------------------------------------------------------------


def _build_dataset(records: list[dict], tokenizer, max_length: int, max_chars: int):
    """Tokenize records and return a HuggingFace Dataset."""
    from datasets import Dataset  # type: ignore

    texts = [_make_text(r, max_chars) for r in records]
    labels = [r["label"] for r in records]

    encodings = tokenizer(
        texts,
        truncation=True,
        padding=True,
        max_length=max_length,
        return_tensors=None,  # return lists; Dataset handles tensors
    )

    data = {
        "input_ids": encodings["input_ids"],
        "attention_mask": encodings["attention_mask"],
        "labels": labels,
    }
    if "token_type_ids" in encodings:
        data["token_type_ids"] = encodings["token_type_ids"]

    return Dataset.from_dict(data)


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


def _make_compute_metrics():
    from sklearn.metrics import f1_score, accuracy_score  # type: ignore
    import numpy as np

    def compute_metrics(eval_pred):
        logits, labels = eval_pred
        preds = np.argmax(logits, axis=-1)
        return {
            "accuracy": float(accuracy_score(labels, preds)),
            "f1": float(f1_score(labels, preds, zero_division=0)),
            "f1_macro": float(f1_score(labels, preds, average="macro", zero_division=0)),
        }

    return compute_metrics


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@click.command()
@click.option("--input", "input_path", default=_INPUT_DEFAULT, show_default=True,
              metavar="PATH", help="JSONL labels file.")
@click.option("--output-dir", default=_OUTPUT_DEFAULT, show_default=True,
              metavar="PATH", help="Directory to save the fine-tuned model.")
@click.option("--model", default=_DEFAULT_MODEL, show_default=True,
              help="HuggingFace model name or local path.")
@click.option("--epochs", default=4, show_default=True, type=int,
              help="Number of training epochs.")
@click.option("--batch-size", default=8, show_default=True, type=int,
              help="Training batch size.")
@click.option("--lr", default=2e-5, show_default=True, type=float,
              help="Learning rate.")
@click.option("--max-length", default=256, show_default=True, type=int,
              help="Max token length (BERT max is 512; shorter = faster).")
@click.option("--max-chars", default=4000, show_default=True, type=int,
              help="Truncate raw text to N chars before tokenisation.")
@click.option("--val-ratio", default=0.2, show_default=True, type=float,
              help="Fraction of data held out for validation.")
@click.option("--seed", default=42, show_default=True, type=int)
@click.option("--only-reviewed", is_flag=True, default=False,
              help="Use only records that have been human-reviewed.")
@click.option("--min-confidence", default=None,
              type=click.Choice(["low", "medium", "high"]),
              help="Minimum Ollama confidence level to include.")
@click.option("--weight-decay", default=0.01, show_default=True, type=float)
@click.option("--warmup-ratio", default=0.1, show_default=True, type=float,
              help="Fraction of steps used for LR warm-up.")
def main(
    input_path: str,
    output_dir: str,
    model: str,
    epochs: int,
    batch_size: int,
    lr: float,
    max_length: int,
    max_chars: int,
    val_ratio: float,
    seed: int,
    only_reviewed: bool,
    min_confidence: Optional[str],
    weight_decay: float,
    warmup_ratio: float,
) -> None:
    """Fine-tune a Romanian BERT model for consultation classification."""

    # --- lazy imports so the module loads without heavy deps installed ---
    try:
        from transformers import (  # type: ignore
            AutoTokenizer,
            AutoModelForSequenceClassification,
            TrainingArguments,
            Trainer,
            DataCollatorWithPadding,
            set_seed,
        )
        from datasets import DatasetDict  # type: ignore
    except ImportError:
        raise click.ClickException(
            "Missing dependencies. Run:\n  pip install transformers torch datasets scikit-learn"
        )

    set_seed(seed)

    # ---- load data --------------------------------------------------------
    path = Path(input_path)
    if not path.exists():
        raise click.ClickException(f"Labels file not found: {path}")

    records = _load_records(path, only_reviewed, min_confidence)

    pos = sum(1 for r in records if r["label"] == 1)
    neg = len(records) - pos

    click.echo(f"Loaded {len(records)} records  (label=1: {pos}, label=0: {neg})")

    if len(records) < 20:
        raise click.ClickException("Too few records to train (<20). Label more articles first.")

    if pos == 0 or neg == 0:
        raise click.ClickException("Only one class present in the dataset — cannot train.")

    if len(records) < 100:
        click.echo(click.style(
            f"Warning: only {len(records)} records — model may overfit. "
            "Consider labeling more articles.", fg="yellow"
        ))

    # ---- split ------------------------------------------------------------
    train_records, val_records = _split(records, val_ratio, seed)
    click.echo(f"Split: {len(train_records)} train / {len(val_records)} val")

    # ---- tokeniser --------------------------------------------------------
    click.echo(f"Loading tokenizer: {model}")
    tokenizer = AutoTokenizer.from_pretrained(model)

    train_dataset = _build_dataset(train_records, tokenizer, max_length, max_chars)
    val_dataset = _build_dataset(val_records, tokenizer, max_length, max_chars)
    dataset = DatasetDict({"train": train_dataset, "validation": val_dataset})

    # ---- model ------------------------------------------------------------
    click.echo(f"Loading model: {model}")
    bert_model = AutoModelForSequenceClassification.from_pretrained(
        model,
        num_labels=2,
        id2label={0: "PRESS_RELEASE", 1: "PUBLIC_CONSULTATION"},
        label2id={"PRESS_RELEASE": 0, "PUBLIC_CONSULTATION": 1},
    )

    # ---- training args ----------------------------------------------------
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    total_steps = (len(train_records) // batch_size) * epochs
    warmup_steps = int(total_steps * warmup_ratio)

    training_args = TrainingArguments(
        output_dir=str(output_path),
        num_train_epochs=epochs,
        per_device_train_batch_size=batch_size,
        per_device_eval_batch_size=batch_size * 2,
        learning_rate=lr,
        weight_decay=weight_decay,
        warmup_steps=warmup_steps,
        eval_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="f1",
        greater_is_better=True,
        logging_steps=10,
        report_to="none",
        seed=seed,
        fp16=False,  # set True if you have a CUDA GPU for ~2x speedup
    )

    data_collator = DataCollatorWithPadding(tokenizer=tokenizer)

    trainer = Trainer(
        model=bert_model,
        args=training_args,
        train_dataset=dataset["train"],
        eval_dataset=dataset["validation"],
        data_collator=data_collator,
        compute_metrics=_make_compute_metrics(),
    )

    # ---- train ------------------------------------------------------------
    click.echo("\nStarting training…")
    trainer.train()

    # ---- final eval -------------------------------------------------------
    click.echo("\nFinal evaluation on validation set:")
    metrics = trainer.evaluate()
    for k, v in metrics.items():
        if isinstance(v, float):
            click.echo(f"  {k}: {v:.4f}")
        else:
            click.echo(f"  {k}: {v}")

    # ---- save -------------------------------------------------------------
    trainer.save_model(str(output_path))
    tokenizer.save_pretrained(str(output_path))

    click.echo(click.style(f"\nModel saved to {output_path.resolve()}", fg="green", bold=True))
    click.echo("\nTo use in inference:")
    click.echo(f'  from transformers import pipeline')
    click.echo(f'  clf = pipeline("text-classification", model="{output_path.resolve()}")')
    click.echo(f'  clf("Consultare publică privind proiectul de hotărâre...")')


if __name__ == "__main__":
    main()
