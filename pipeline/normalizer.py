"""Text normalisation utilities."""

from __future__ import annotations

import re
import unicodedata

from bs4 import BeautifulSoup


def normalize(text: str) -> tuple[str, str]:
    """Strip HTML, collapse whitespace.

    Returns ``(normalized, lowercased)`` where *normalized* preserves original
    casing and *lowercased* is a copy used for keyword matching.
    """
    # Strip HTML tags
    soup = BeautifulSoup(text, "lxml")
    plain = soup.get_text(separator=" ")

    # Remove control characters (except standard whitespace)
    plain = "".join(
        ch for ch in plain
        if unicodedata.category(ch)[0] != "C" or ch in "\t\n\r "
    )

    # Collapse whitespace
    plain = re.sub(r"[ \t]+", " ", plain)
    plain = re.sub(r"\n{3,}", "\n\n", plain)
    plain = plain.strip()

    return plain, plain.lower()
