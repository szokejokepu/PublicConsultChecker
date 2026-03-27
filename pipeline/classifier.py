"""Cosine-similarity BERT classifier for public-consultation detection."""

from __future__ import annotations

MODEL_NAME = "dumitrescustefan/bert-base-romanian-cased-v1"

POSITIVE_REFS: list[str] = [
    "Anunțăm organizarea unei dezbateri publice privind proiectul de hotărâre",
    "Se convoacă audierea publică a cetățenilor referitoare la",
    "Consultare publică privind proiectul de buget al municipiului",
    "Invitație la ședința publică de dezbatere a planului urbanistic",
    "Anunț public: supunem dezbaterii publice următorul proiect",
]

# Module-level lazy singletons (populated on first call)
_tokenizer = None
_model = None
_ref_embeddings = None  # torch.Tensor once loaded


def _embed(texts: list[str]):
    """Return mean-pooled, L2-normalised embeddings, shape (N, hidden)."""
    import torch
    import torch.nn.functional as F

    enc = _tokenizer(
        texts,
        padding=True,
        truncation=True,
        max_length=512,
        return_tensors="pt",
    )
    with torch.no_grad():
        out = _model(**enc)
    mask = enc["attention_mask"].unsqueeze(-1).float()
    embeddings = (out.last_hidden_state * mask).sum(1) / mask.sum(1)
    return F.normalize(embeddings, dim=-1)


def _load():
    global _tokenizer, _model, _ref_embeddings
    if _tokenizer is None:
        from transformers import AutoModel, AutoTokenizer

        _tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
        _model = AutoModel.from_pretrained(MODEL_NAME)
        _model.eval()
        _ref_embeddings = _embed(POSITIVE_REFS)
    return _tokenizer, _model, _ref_embeddings


def classify(text: str, threshold: float = 0.65) -> tuple[bool, float]:
    """Return ``(is_positive, mean_cosine_score)`` for *text*."""
    import torch

    _load()
    text_emb = _embed([text])                        # shape (1, hidden)
    scores = (text_emb @ _ref_embeddings.T).squeeze(0)  # shape (N,)
    mean_score = scores.mean().item()
    return mean_score >= threshold, mean_score
