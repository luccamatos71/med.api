import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.models.base import Base


class ExamSession(Base):
    """A generated multiple-choice exam (simulado) over a subject or topic."""

    __tablename__ = "exam_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    scope_type = Column(String, nullable=False)  # 'subject' | 'topic'
    scope_id = Column(UUID(as_uuid=True), nullable=False)
    scope_name = Column(String, nullable=True)
    num_questions = Column(Integer, nullable=False, default=10)
    status = Column(String, nullable=False, default="in_progress")  # in_progress | finished
    score = Column(Float, nullable=True)  # 0-100
    duration_seconds = Column(Integer, nullable=True)
    # questions_json: [{stem, options[4], correct_index, explanation, source}]
    questions_json = Column(JSONB, nullable=False)
    # answers_json: {"0": 2, "1": 0, ...} (question index -> chosen option index)
    answers_json = Column(JSONB, nullable=True)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    finished_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_exam_sessions_user_id", "user_id"),
        Index("ix_exam_sessions_scope_id", "scope_id"),
    )
