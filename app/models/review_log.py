import uuid
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, Column, DateTime, Float, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID

from app.models.base import Base


class ReviewLog(Base):
    __tablename__ = "review_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    flashcard_id = Column(
        UUID(as_uuid=True), ForeignKey("flashcards.id", ondelete="CASCADE"), nullable=False
    )
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    rating = Column(String, nullable=False)
    review_time = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    stability_before = Column(Float, nullable=True)
    stability_after = Column(Float, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "rating IN ('again', 'hard', 'good', 'easy')",
            name="ck_review_logs_rating",
        ),
        Index("ix_review_logs_flashcard_id", "flashcard_id"),
    )
