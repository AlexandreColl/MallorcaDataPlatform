"""The language of an answer, from the ``Accept-Language`` header (ADR 0024).

Only the catalogue's texts change with it (labels and licences of the sources, ``gold.dim_source_texts``): codes,
numbers and the names of places are the same in every language. Spanish is the reference and the fallback.
"""

from __future__ import annotations

LANGUAGES = ("es", "ca", "en")
DEFAULT = "es"


def _quality(params: str) -> float:
    """The ``q`` of a language range (``;q=0.8``); 1 when absent, 0 when it does not read as a number."""
    for param in params.split(";"):
        name, _, value = param.strip().partition("=")
        if name.strip().lower() == "q":
            try:
                return float(value)
            except ValueError:
                return 0.0
    return 1.0


def negotiate(header: str | None) -> str:
    """The language of ``LANGUAGES`` the client prefers: ``"ca-ES,ca;q=0.9,en;q=0.8"`` is ``ca``.

    Ranges are compared by their primary subtag (``ca-ES-valencia`` is Catalan) and their ``q``; on a tie the first
    one wins. ``*``, unknown languages and ``q=0`` are ignored, and Spanish answers when nothing fits.
    """
    best, best_quality = DEFAULT, 0.0
    for part in (header or "").split(","):
        tag, _, params = part.partition(";")
        language = tag.strip().lower().split("-")[0]
        quality = _quality(params)
        if language in LANGUAGES and quality > best_quality:
            best, best_quality = language, quality
    return best
