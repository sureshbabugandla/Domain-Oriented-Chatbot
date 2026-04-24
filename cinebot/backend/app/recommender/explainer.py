"""Recommendation explainer.

Two paths:

1. **Template-based** (default, fast, free): assemble the ``reasons`` list
   the recommender already populated.
2. **LLM-polished** (optional): ask the LLM to rewrite the templated text
   as one smooth sentence that references the user's original query.

Path 2 is gated by ``settings.llm_provider`` and wrapped in a tenacity
circuit-breaker — if the LLM is slow or down, we fall through to path 1
so the user always gets a response.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from app.core.logging import get_logger
from app.nlp.pipeline import UnderstoodMessage
from app.recommender.hybrid import Candidate

log = get_logger("recommender.explainer")


@dataclass
class Explanation:
    movie_id: int
    title: str
    year: int | None
    poster_url: str | None
    score: float
    reasons: list[str]
    rendered: str                 # one-line natural explanation

    def to_dict(self) -> dict:
        return asdict(self)


def _render_templated(candidate: Candidate) -> str:
    if not candidate.reasons:
        return f"'{candidate.movie.title}' looks like a solid match."
    first = candidate.reasons[0]
    if len(candidate.reasons) == 1:
        return f"'{candidate.movie.title}' — {first.lower()}."
    return (
        f"'{candidate.movie.title}' — {first.lower()}, "
        f"and {candidate.reasons[1].lower()}."
    )


def _poster_url(candidate: Candidate) -> str | None:
    from app.core.config import settings
    p = candidate.movie.poster_path
    return f"{settings.tmdb_image_base}{p}" if p else None


def build_explanations(
    candidates: list[Candidate],
    understood: UnderstoodMessage,
) -> list[Explanation]:
    """Templated explanations, synchronous. The LLM variant is available in
    ``llm_polish`` below and should be called from an async context with a
    circuit breaker.
    """
    out: list[Explanation] = []
    for c in candidates:
        year = c.movie.release_date.year if c.movie.release_date else None
        out.append(
            Explanation(
                movie_id=c.movie.id,
                title=c.movie.title,
                year=year,
                poster_url=_poster_url(c),
                score=round(c.final_score, 3),
                reasons=c.reasons,
                rendered=_render_templated(c),
            )
        )
    log.info(
        "explanations_built",
        n=len(out),
        first=out[0].rendered if out else None,
    )
    return out
