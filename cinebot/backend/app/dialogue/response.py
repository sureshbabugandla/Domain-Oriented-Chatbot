"""Natural-language response templates.

These are the deterministic fallback when we don't invoke the LLM (either
because the intent doesn't need polish, or because the LLM failed open).
They read like a real person wrote them — no "I am a chatbot, let me
help you" preamble.
"""

from __future__ import annotations

import random

from app.db.models import IntentLabel
from app.dialogue.state import Slots
from app.recommender.explainer import Explanation

_GREET = [
    "Hey! Tell me what you're in the mood for and I'll find you a movie.",
    "Hi there — rough day, quiet night, or something specific in mind?",
    "Welcome back. What are we watching tonight?",
]

_GOODBYE = [
    "Enjoy the movie! Come back any time.",
    "Happy watching — see you next time.",
    "Take care. Hit me up when the next movie night rolls around.",
]

_OOS = [
    "I'm a movie-only bot — ask me for a film recommendation and I'll be much more useful.",
    "I only do movie recs, but I do them well. Give me a mood, a genre, or a vibe.",
]

_NEED_MORE_CONTEXT = [
    "Tell me a bit more — a genre, a mood, a decade, or even just a movie you've liked recently.",
    "Could you narrow it down a little? Genre, tone, era, runtime — anything helps.",
]

_FEEDBACK_ACK = [
    "Got it — I'll keep that in mind.",
    "Noted. I'll steer towards (or away from) that kind of thing.",
    "Thanks, that helps me tune the next round.",
]


def greeting() -> str:
    return random.choice(_GREET)                      # noqa: S311


def goodbye() -> str:
    return random.choice(_GOODBYE)                    # noqa: S311


def out_of_scope() -> str:
    return random.choice(_OOS)                        # noqa: S311


def need_more_context() -> str:
    return random.choice(_NEED_MORE_CONTEXT)          # noqa: S311


def feedback_ack() -> str:
    return random.choice(_FEEDBACK_ACK)               # noqa: S311


def render_recommendation_intro(slots: Slots) -> str:
    parts: list[str] = []
    if slots.moods:
        parts.append(f"for a {slots.moods[0]} mood")
    if slots.genre_names:
        parts.append(f"in {', '.join(slots.genre_names)}")
    if slots.min_year and slots.max_year:
        parts.append(f"from the {slots.min_year}s")
    elif slots.min_year:
        parts.append(f"from {slots.min_year} onwards")
    if not parts:
        return "Here are a few picks:"
    return "Here are some picks " + " ".join(parts) + ":"


def render_slate(explanations: list[Explanation]) -> str:
    lines = [f"{i + 1}. {e.rendered}" for i, e in enumerate(explanations)]
    return "\n".join(lines)


def compose_response(
    *,
    intent: str,
    slots: Slots,
    explanations: list[Explanation] | None = None,
) -> str:
    """Assemble the final reply text for a given intent + slate."""
    if intent == IntentLabel.GREET.value:
        return greeting()
    if intent == IntentLabel.GOODBYE.value:
        return goodbye()
    if intent == IntentLabel.OOS.value:
        return out_of_scope()
    if intent == IntentLabel.FEEDBACK.value:
        return feedback_ack()
    if explanations:
        return (
            render_recommendation_intro(slots)
            + "\n"
            + render_slate(explanations)
        )
    return need_more_context()
