import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, Date, DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.models.base import Base


class StudyPlan(Base):
    """An AI-distributed study schedule up to an exam date."""

    __tablename__ = "study_plans"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    exam_date = Column(Date, nullable=False)
    status = Column(String, nullable=False, default="active")  # active | archived
    # plan_json: { overview, summary, days: [{date, tasks:[{type,label,topic_id,subject_id}]}] }
    plan_json = Column(JSONB, nullable=False)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    __table_args__ = (Index("ix_study_plans_user_id", "user_id"),)
