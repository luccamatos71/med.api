"""add topic summaries

Revision ID: 0014
Revises: 0013
Create Date: 2026-06-03
"""

from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS topic_summaries (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            topic_id UUID NOT NULL UNIQUE REFERENCES topics(id) ON DELETE CASCADE,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            summary_json JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_topic_summaries_topic_id ON topic_summaries (topic_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS topic_summaries")
