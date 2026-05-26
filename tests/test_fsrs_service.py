from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from app.services.fsrs_service import apply_rating, preview_intervals


def _review_stub(state: str = "new"):
    return SimpleNamespace(
        flashcard_id=uuid4(),
        state=state,
        stability=None,
        difficulty=None,
        due_date=datetime.now(timezone.utc),
        last_review=None,
        elapsed_days=0,
        scheduled_days=0,
        reps=0,
        lapses=0,
    )


def test_preview_intervals_returns_all_rating_options():
    review = _review_stub()
    intervals = preview_intervals(review)

    assert len(intervals) == 4
    assert [item["rating"] for item in intervals] == ["again", "hard", "good", "easy"]


def test_apply_rating_updates_state_and_counters():
    review = _review_stub()
    now = datetime.now(timezone.utc)
    updated = apply_rating(review, "good", now=now)

    assert updated.state in ("learning", "review", "relearning")
    assert updated.reps == 1
    assert updated.lapses == 0
    assert updated.due_date >= now
    assert updated.stability is not None
    assert updated.difficulty is not None


def test_apply_rating_again_increments_lapses():
    review = _review_stub(state="review")
    review.stability = 2.0
    review.difficulty = 4.0
    review.last_review = datetime.now(timezone.utc)

    updated = apply_rating(review, "again")
    assert updated.reps == 1
    assert updated.lapses == 1
