"""Romanian NER extraction for public-consultation fields."""

from __future__ import annotations

import re

MODEL_NAME = "dumitrescustefan/bert-base-romanian-ner"

# Lazy singleton
_ner_pipeline = None

_SUBJECT_RE = re.compile(
    r"(?:privind|referitor\s+la|cu\s+tema|cu\s+subiectul)\s+([^.\n]+)",
    re.IGNORECASE,
)


def _load():
    global _ner_pipeline
    if _ner_pipeline is None:
        from transformers import pipeline as hf_pipeline

        _ner_pipeline = hf_pipeline(
            "ner",
            model=MODEL_NAME,
            aggregation_strategy="simple",
        )
    return _ner_pipeline


def extract_entities(text: str) -> dict[str, str | None]:
    """Run NER on *text* and return extracted fields."""
    ner = _load()
    entities = ner(text[:512])  # truncate to avoid OOM on huge texts

    extracted_date: str | None = None
    extracted_time: str | None = None
    extracted_place: str | None = None

    for ent in entities:
        label = ent.get("entity_group", "")
        word = ent.get("word", "").strip()
        if label == "DATE" and extracted_date is None:
            extracted_date = word
        elif label == "TIME" and extracted_time is None:
            extracted_time = word
        elif label in ("LOC", "GPE") and extracted_place is None:
            extracted_place = word

    # Subject heuristic
    extracted_subject: str | None = None
    m = _SUBJECT_RE.search(text)
    if m:
        extracted_subject = m.group(1).strip()

    return {
        "extracted_date": extracted_date,
        "extracted_time": extracted_time,
        "extracted_place": extracted_place,
        "extracted_subject": extracted_subject,
    }
