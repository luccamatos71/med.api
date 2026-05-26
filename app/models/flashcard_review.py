import uuid
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, Column, DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID

from app.models.base import Base


class FlashcardReview(Base):
    __tablename__ = "flashcard_reviews"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    flashcard_id = Column(
        UUID(as_uuid=True), ForeignKey("flashcards.id", ondelete="CASCADE"), nullable=False
    )
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    stability = Column(Float, nullable=True)
    difficulty = Column(Float, nullable=True)
    elapsed_days = Column(Integer, nullable=False, default=0)
    scheduled_days = Column(Integer, nullable=False, default=0)
    reps = Column(Integer, nullable=False, default=0)
    lapses = Column(Integer, nullable=False, default=0)
    state = Column(String, nullable=False, default="new")
    last_review = Column(DateTime(timezone=True), nullable=True)
    due_date = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "state IN ('new', 'learning', 'review', 'relearning')",
            name="ck_flashcard_reviews_state",
        ),
        Index("ix_flashcard_reviews_flashcard_id", "flashcard_id", unique=True),
    )
