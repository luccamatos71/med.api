import uuid
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID

from app.models.base import Base


class Flashcard(Base):
    __tablename__ = "flashcards"

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
    doubt_id = Column(
        UUID(as_uuid=True), ForeignKey("doubts.id", ondelete="SET NULL"), nullable=True
    )
    source = Column(String, nullable=False, default="manual")
    front = Column(Text, nullable=False)
    back = Column(Text, nullable=False)
    source_snippet = Column(Text, nullable=True)
    page_number = Column(Integer, nullable=True)
    ai_approved_at = Column(DateTime(timezone=True), nullable=True)
    archived_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "source IN ('ai_generated', 'manual', 'from_doubt')",
            name="ck_flashcards_source",
        ),
    )
