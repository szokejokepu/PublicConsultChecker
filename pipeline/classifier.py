"""Cosine-similarity BERT classifier for public-consultation detection."""

from __future__ import annotations

DEFAULT_MODEL_NAME = "dumitrescustefan/bert-base-romanian-cased-v1"

DEFAULT_POSITIVE_REFS: list[str] = [
    "Anunțăm organizarea unei dezbateri publice privind proiectul de hotărâre",
    "Se convoacă audierea publică a cetățenilor referitoare la",
    "Consultare publică privind proiectul de buget al municipiului",
    "Invitație la ședința publică de dezbatere a planului urbanistic",
    "Anunț public: supunem dezbaterii publice următorul proiect",
]

# Cache keyed by (model_name, tuple(positive_refs))
_cache: dict = {}


def _embed(tokenizer, model, texts: list[str]):
    """Return mean-pooled, L2-normalised embeddings, shape (N, hidden)."""
    import torch
    import torch.nn.functional as F

    enc = tokenizer(
        texts,
        padding=True,
        truncation=True,
        max_length=512,
        return_tensors="pt",
    )
    with torch.no_grad():
        out = model(**enc)
    mask = enc["attention_mask"].unsqueeze(-1).float()
    embeddings = (out.last_hidden_state * mask).sum(1) / mask.sum(1)
    return F.normalize(embeddings, dim=-1)


def _load(model_name: str, positive_refs: list[str]):
    key = (model_name, tuple(positive_refs))
    if key not in _cache:
        from transformers import AutoModel, AutoTokenizer
        tokenizer = AutoTokenizer.from_pretrained(model_name)
        model = AutoModel.from_pretrained(model_name)
        model.eval()
        ref_embeddings = _embed(tokenizer, model, positive_refs)
        _cache[key] = (tokenizer, model, ref_embeddings)
    return _cache[key]


def classify(
    text: str,
    threshold: float = 0.65,
    model_name: str = DEFAULT_MODEL_NAME,
    positive_refs: list[str] | None = None,
) -> tuple[bool, float]:
    """Return ``(is_positive, mean_cosine_score)`` for *text*."""
    refs = positive_refs if positive_refs is not None else DEFAULT_POSITIVE_REFS
    tokenizer, model, ref_embeddings = _load(model_name, refs)
    text_emb = _embed(tokenizer, model, [text])           # shape (1, hidden)
    scores = (text_emb @ ref_embeddings.T).squeeze(0)     # shape (N,)
    mean_score = scores.mean().item()
    return mean_score >= threshold, mean_score
