"""Romanian keyword filter for public-consultation detection."""

from __future__ import annotations

KEYWORDS: list[str] = [
    "dezbatere publică",
    "consultare publică",
    "audiere publică",
    "ședință publică",
    "supuse dezbaterii",
    "anunț public",
]


def keyword_filter(lowercased_text: str) -> tuple[bool, list[str]]:
    """Check *lowercased_text* for public-consultation keywords.

    Returns ``(matched, keywords_found)``.
    """
    found = [kw for kw in KEYWORDS if kw in lowercased_text]
    return bool(found), found
