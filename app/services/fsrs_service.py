from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fsrs import Card, Rating, Scheduler, State

from app.models.flashcard_review import FlashcardReview

FSRS_SCHEDULER = Scheduler(enable_fuzzing=False)

RATING_MAP = {
    "again": Rating.Again,
    "hard": Rating.Hard,
    "good": Rating.Good,
    "easy": Rating.Easy,
}

REVERSE_STATE_MAP = {
    State.Learning: "learning",
    State.Review: "review",
    State.Relearning: "relearning",
}


def _state_to_fsrs(state: str) -> State:
    if state in ("new", "learning"):
        return State.Learning
    if state == "review":
        return State.Review
    return State.Relearning


def _card_id_from_review(review: FlashcardReview) -> int:
    return int(review.flashcard_id.int % (2**31 - 1))


def build_fsrs_card(review: FlashcardReview) -> Card:
    fsrs_state = _state_to_fsrs(review.state)
    step = 0 if fsrs_state in (State.Learning, State.Relearning) else None
    return Card(
        card_id=_card_id_from_review(review),
        state=fsrs_state,
        step=step,
        stability=review.stability,
        difficulty=review.difficulty,
        due=review.due_date or datetime.now(timezone.utc),
        last_review=review.last_review,
    )


def format_interval_label(now: datetime, next_due: datetime) -> str:
    delta = max(next_due - now, timedelta(0))
    if delta.total_seconds() < 60:
        return "<1m"
    minutes = int(delta.total_seconds() // 60)
    if minutes < 60:
        return f"{minutes}m"
    hours = int(delta.total_seconds() // 3600)
    if hours < 24:
        return f"{hours}h"
    days = int(delta.total_seconds() // 86400)
    if days < 7:
        return f"{days}d"
    weeks = round(days / 7)
    if weeks < 5:
        return f"{weeks}sem"
    months = round(days / 30)
    return f"{months}m"


def preview_intervals(review: FlashcardReview, now: datetime | None = None) -> list[dict[str, str]]:
    current = now or datetime.now(timezone.utc)
    card = build_fsrs_card(review)
    previews: list[dict[str, str]] = []
    for key in ("again", "hard", "good", "easy"):
        updated, _ = FSRS_SCHEDULER.review_card(card, RATING_MAP[key], current)
        previews.append(
            {
                "rating": key,
                "label": key.capitalize(),
                "interval": format_interval_label(current, updated.due),
            }
        )
    return previews


def apply_rating(review: FlashcardReview, rating: str, now: datetime | None = None) -> FlashcardReview:
    current = now or datetime.now(timezone.utc)
    previous_review = review.last_review
    card = build_fsrs_card(review)
    updated_card, _ = FSRS_SCHEDULER.review_card(card, RATING_MAP[rating], current)

    review.stability = updated_card.stability
    review.difficulty = updated_card.difficulty
    review.due_date = updated_card.due
    review.last_review = updated_card.last_review
    review.state = REVERSE_STATE_MAP.get(updated_card.state, "review")

    review.elapsed_days = max((current.date() - previous_review.date()).days, 0) if previous_review else 0
    review.scheduled_days = max((updated_card.due.date() - current.date()).days, 0)
    review.reps = max(review.reps, 0) + 1
    if rating == "again":
        review.lapses = max(review.lapses, 0) + 1
    return review
