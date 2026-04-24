"""Unit tests for the entity extractor.

These are pure functions over strings — no DB, no ML — so they run in
milliseconds and are the foundation of the >80% coverage goal.
"""

from __future__ import annotations

import pytest

from app.nlp.entity_extractor import extract


@pytest.mark.unit
class TestMoodExtraction:
    def test_feeling_sad_detected(self) -> None:
        ents = extract("I'm feeling sad, suggest a feel-good movie")
        assert "sad" in ents.moods
        # Sad should expand to uplifting/hopeful descriptors.
        assert any(d in {"uplifting", "heartwarming", "hopeful"} for d in ents.descriptors)

    def test_multiple_moods(self) -> None:
        ents = extract("I'm stressed and bored")
        assert {"stressed", "bored"} <= set(ents.moods)

    def test_no_mood_on_neutral_text(self) -> None:
        ents = extract("recommend a sci-fi film")
        assert ents.moods == []


@pytest.mark.unit
class TestGenreExtraction:
    @pytest.mark.parametrize(
        "text,expected_id",
        [
            ("action movie from the 90s", 28),
            ("some sci-fi please", 878),
            ("science fiction recommendations", 878),
            ("feel-good comedy", 35),
            ("scary horror film", 27),
            ("romantic drama", 10749),
        ],
    )
    def test_genre_aliases(self, text: str, expected_id: int) -> None:
        ents = extract(text)
        assert expected_id in ents.genre_ids

    def test_longest_match_wins(self) -> None:
        """'science fiction' should resolve before 'science' or 'fiction' alone."""
        ents = extract("science fiction movie")
        assert 878 in ents.genre_ids


@pytest.mark.unit
class TestYearExtraction:
    def test_decade(self) -> None:
        ents = extract("action movies from the 1980s")
        assert ents.min_year == 1980
        assert ents.max_year == 1989

    def test_year_range(self) -> None:
        ents = extract("something between 1995 and 2005")
        assert ents.min_year == 1995
        assert ents.max_year == 2005

    def test_single_year(self) -> None:
        ents = extract("what came out in 2010")
        assert ents.min_year == 2010


@pytest.mark.unit
class TestOtherEntities:
    def test_age(self) -> None:
        assert extract("movies for a 12-year-old").age == 12
        assert extract("something for my 7 year old").age == 7

    def test_max_runtime(self) -> None:
        assert extract("anything under 90 minutes").max_runtime == 90
        assert extract("less than 120 min please").max_runtime == 120

    def test_min_rating(self) -> None:
        assert extract("rated at least 8").min_rating == 8.0
        assert extract("rating over 7.5").min_rating == 7.5

    def test_language(self) -> None:
        ents = extract("Japanese animation")
        assert "ja" in ents.languages

    def test_empty(self) -> None:
        ents = extract("")
        assert ents.to_dict() == {}
