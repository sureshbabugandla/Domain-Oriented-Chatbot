"""Entity extraction for movie-recommendation queries.

We combine spaCy NER (for dates, languages, generic entities) with
hand-tuned gazetteers and regexes (for moods, genres, decades). The
gazetteer-first approach is deliberate — it gives us tight precision on
the vocabulary we care about, and we fall back to spaCy only when that
misses. 500 labeled examples don't support training a full NER model to
production quality; a curated lookup does.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache

import spacy
from spacy.language import Language

from app.core.config import settings


# ── Gazetteers ────────────────────────────────────────────
MOOD_TO_DESCRIPTORS: dict[str, list[str]] = {
    # mood token → semantic keywords fed into the embedding query
    "happy":        ["feel-good", "uplifting", "comedy"],
    "sad":          ["uplifting", "heartwarming", "hopeful"],
    "stressed":     ["relaxing", "gentle", "cozy"],
    "bored":        ["thrilling", "fast-paced", "action"],
    "excited":      ["thrilling", "action", "adventure"],
    "nostalgic":    ["classic", "retro", "coming-of-age"],
    "romantic":     ["romance", "love story"],
    "thoughtful":   ["cerebral", "thought-provoking", "drama"],
    "scared":       ["comforting", "wholesome"],
    "angry":        ["cathartic", "revenge"],
    "lonely":       ["heartwarming", "friendship"],
}
_MOOD_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(rf"\b(?:i['']?m|i am|feeling|feel)\s+(?:a bit |kind of |really |very )?({w})\b", re.I), w)
    for w in MOOD_TO_DESCRIPTORS
]
_MOOD_PATTERNS += [
    (re.compile(rf"\b({w})\b", re.I), w) for w in MOOD_TO_DESCRIPTORS
]

# TMDB canonical genre ids — keep these aligned with the ingest script.
GENRE_ALIASES: dict[str, int] = {
    "action": 28,
    "adventure": 12,
    "animation": 16, "animated": 16, "anime": 16,
    "comedy": 35, "funny": 35, "comedies": 35,
    "crime": 80,
    "documentary": 99, "docu": 99,
    "drama": 18,
    "family": 10751,
    "fantasy": 14,
    "history": 36, "historical": 36,
    "horror": 27, "scary": 27,
    "music": 10402, "musical": 10402,
    "mystery": 9648,
    "romance": 10749, "romantic": 10749, "rom-com": 10749,
    "sci-fi": 878, "science fiction": 878, "scifi": 878,
    "thriller": 53,
    "war": 10752,
    "western": 37,
}

_DECADE_RE = re.compile(r"\b(19[3-9]0|20[0-2]0)s\b")
_YEAR_RE = re.compile(r"\b(19[3-9]\d|20[0-2]\d)\b")
_AGE_RE = re.compile(r"\b(\d{1,2})[- ]?year[- ]?old\b", re.I)
_RUNTIME_RE = re.compile(r"\b(under|less than|at most)\s+(\d{2,3})\s*(?:min|mins|minutes?)\b", re.I)
_MIN_RATING_RE = re.compile(r"\b(?:rated|rating)\s*(?:at least|over|above|>=?)\s*(\d(?:\.\d)?)\b", re.I)
_LANG_RE = re.compile(r"\b(english|spanish|french|german|italian|japanese|korean|hindi|mandarin)\b", re.I)
_LANG_CODES = {
    "english": "en", "spanish": "es", "french": "fr", "german": "de",
    "italian": "it", "japanese": "ja", "korean": "ko", "hindi": "hi",
    "mandarin": "zh",
}


@dataclass
class Entities:
    moods: list[str] = field(default_factory=list)
    genre_ids: list[int] = field(default_factory=list)
    genre_names: list[str] = field(default_factory=list)
    min_year: int | None = None
    max_year: int | None = None
    max_runtime: int | None = None
    min_rating: float | None = None
    age: int | None = None
    languages: list[str] = field(default_factory=list)
    descriptors: list[str] = field(default_factory=list)   # mood→descriptor expansion

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v not in (None, [], "")}


@lru_cache(maxsize=1)
def _nlp() -> Language:
    return spacy.load(settings.spacy_model, disable=["parser", "tagger"])


def _extract_genres(text: str) -> tuple[list[int], list[str]]:
    ids: list[int] = []
    names: list[str] = []
    # Longest match first to catch "science fiction" before "fiction".
    for alias in sorted(GENRE_ALIASES, key=len, reverse=True):
        if re.search(rf"\b{re.escape(alias)}\b", text, re.I):
            gid = GENRE_ALIASES[alias]
            if gid not in ids:
                ids.append(gid)
                names.append(alias)
    return ids, names


def _extract_moods(text: str) -> list[str]:
    found: list[str] = []
    for pat, mood in _MOOD_PATTERNS:
        if pat.search(text) and mood not in found:
            found.append(mood)
    return found


def _extract_years(text: str) -> tuple[int | None, int | None]:
    # Decades take precedence over bare years.
    dec = _DECADE_RE.search(text)
    if dec:
        base = int(dec.group(1))
        return base, base + 9
    years = [int(y) for y in _YEAR_RE.findall(text)]
    if len(years) >= 2:
        return min(years), max(years)
    if len(years) == 1:
        return years[0], None
    return None, None


def extract(text: str) -> Entities:
    """Extract all entities from a raw user utterance."""
    ent = Entities()

    ent.moods = _extract_moods(text)
    for m in ent.moods:
        for d in MOOD_TO_DESCRIPTORS[m]:
            if d not in ent.descriptors:
                ent.descriptors.append(d)

    ent.genre_ids, ent.genre_names = _extract_genres(text)
    ent.min_year, ent.max_year = _extract_years(text)

    if age_match := _AGE_RE.search(text):
        ent.age = int(age_match.group(1))

    if rt_match := _RUNTIME_RE.search(text):
        ent.max_runtime = int(rt_match.group(2))

    if mr_match := _MIN_RATING_RE.search(text):
        ent.min_rating = float(mr_match.group(1))

    for lang_match in _LANG_RE.finditer(text):
        code = _LANG_CODES[lang_match.group(1).lower()]
        if code not in ent.languages:
            ent.languages.append(code)

    # spaCy pass for DATE entities we might have missed (e.g., "last year").
    doc = _nlp()(text)
    for e in doc.ents:
        if e.label_ == "DATE" and e.text.isdigit() and len(e.text) == 4:
            y = int(e.text)
            if ent.min_year is None and 1930 <= y <= 2030:
                ent.min_year = y

    return ent
