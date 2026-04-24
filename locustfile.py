"""Locust load test.

Simulates realistic traffic: each user logs in once, then alternates between
chat and feedback with human-plausible thinking time. Run via `make load-test`.

The queries are drawn from a varied pool so the NLP pipeline's intent
classifier and entity extractor both get exercised.
"""

from __future__ import annotations

import random
import uuid
from typing import Any

from locust import HttpUser, between, task

QUERIES = [
    "I'm feeling sad, suggest a feel-good movie",
    "something funny from the 90s",
    "recommend a sci-fi thriller under 2 hours",
    "what should I watch tonight",
    "Japanese animation for kids",
    "slow-burn mystery rated over 8",
    "something short and scary",
    "romantic comedy for date night",
    "mind-bending sci-fi please",
    "cozy Sunday afternoon rewatch",
]

REFINES = [
    "more like the second one",
    "anything else like that",
    "show me something similar but newer",
    "another one please",
]

GREETINGS = ["hi", "hey", "hello there"]
GOODBYES = ["thanks, bye", "that's all for now", "catch you later"]


class CineBotUser(HttpUser):
    wait_time = between(2, 8)
    session_id: str | None = None
    token: str | None = None

    def on_start(self) -> None:
        """Register + login once per simulated user."""
        email = f"locust+{uuid.uuid4().hex[:10]}@example.com"
        password = "locust-test-password"
        # Register — tolerate 409 in case of collision.
        self.client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": password, "display_name": "Locust"},
            name="/auth/register",
        )
        resp = self.client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": password},
            name="/auth/login",
        )
        if resp.status_code == 200:
            self.token = resp.json()["access_token"]

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    @task(1)
    def greet(self) -> None:
        self._chat(random.choice(GREETINGS))

    @task(8)
    def recommend(self) -> None:
        # Start a fresh session most of the time (cold-path).
        if random.random() < 0.3:
            self.session_id = None
        self._chat(random.choice(QUERIES))

    @task(3)
    def refine(self) -> None:
        if self.session_id is None:
            return
        self._chat(random.choice(REFINES))

    @task(2)
    def feedback(self) -> None:
        if self.session_id is None:
            return
        self.client.post(
            "/api/v1/feedback",
            json={
                "session_id": self.session_id,
                "movie_id": random.randint(1, 999),
                "signal": random.choice(["like", "dislike", "click", "dismiss"]),
            },
            headers=self._headers(),
            name="/feedback",
        )

    @task(1)
    def goodbye(self) -> None:
        self._chat(random.choice(GOODBYES))

    def _chat(self, message: str) -> None:
        resp = self.client.post(
            "/api/v1/chat",
            json={"session_id": self.session_id, "message": message},
            headers=self._headers(),
            name="/chat",
        )
        if resp.status_code == 200:
            data: dict[str, Any] = resp.json()
            self.session_id = data.get("session_id")
