"""Text preprocessing — cheap, deterministic, no ML.

Runs before both the intent classifier and the embedder. spaCy does the
lemmatization; everything else is stdlib.
"""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache

import spacy
from spacy.language import Language

from app.core.config import settings

_WHITESPACE = re.compile(r"\s+")
_URL = re.compile(r"https?://\S+|www\.\S+")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


@lru_cache(maxsize=1)
def _nlp() -> Language:
    # Disable heavy components — we only need tokenizer + lemmatizer here.
    return spacy.load(settings.spacy_model, disable=["parser", "ner", "tagger"])


def normalize(text: str) -> str:
    """Unicode NFKC, strip control chars + URLs, collapse whitespace."""
    if not text:
        return ""
    t = unicodedata.normalize("NFKC", text)
    t = _URL.sub(" ", t)
    t = _CONTROL.sub(" ", t)
    t = _WHITESPACE.sub(" ", t).strip()
    return t


def preprocess(text: str, *, lemmatize: bool = False) -> str:
    """Normalize + optionally lemmatize + lowercase."""
    t = normalize(text).lower()
    if not lemmatize:
        return t
    doc = _nlp()(t)
    return " ".join(tok.lemma_ for tok in doc if not tok.is_space)
