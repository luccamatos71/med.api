import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID

from app.models.base import Base


class Doubt(Base):
    __tablename__ = "doubts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    topic_id = Column(
        UUID(as_uuid=True), ForeignKey("topics.id", ondelete="CASCADE"), nullable=False, index=True
    )
    material_id = Column(
        UUID(as_uuid=True), ForeignKey("materials.id", ondelete="SET NULL"), nullable=True
    )
    question = Column(Text, nullable=False)
    ai_answer = Column(Text, nullable=True)
    status = Column(String, nullable=False, default="pending")
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    flashcard_id = Column(
        UUID(as_uuid=True), ForeignKey("flashcards.id", ondelete="SET NULL"), nullable=True
    )
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_doubts_user_id", "user_id"),
        Index("ix_doubts_topic_id", "topic_id"),
        Index("ix_doubts_status", "status"),
    )
