from app.models import Base, FlashcardReview, ReviewLog


def test_flashcard_review_model_defines_fsrs_state_contract():
    table = Base.metadata.tables[FlashcardReview.__tablename__]

    assert set(
        [
            "id",
            "flashcard_id",
            "user_id",
            "stability",
            "difficulty",
            "elapsed_days",
            "scheduled_days",
            "reps",
            "lapses",
            "state",
            "last_review",
            "due_date",
        ]
    ).issubset(table.columns.keys())

    index = next(index for index in table.indexes if index.name == "ix_flashcard_reviews_flashcard_id")
    assert index.unique is True
    assert "ck_flashcard_reviews_state" in {constraint.name for constraint in table.constraints}


def test_review_log_model_defines_rating_audit_contract():
    table = Base.metadata.tables[ReviewLog.__tablename__]

    assert set(
        [
            "id",
            "flashcard_id",
            "user_id",
            "rating",
            "review_time",
            "stability_before",
            "stability_after",
        ]
    ).issubset(table.columns.keys())

    assert "ix_review_logs_flashcard_id" in {index.name for index in table.indexes}
    assert "ck_review_logs_rating" in {constraint.name for constraint in table.constraints}
