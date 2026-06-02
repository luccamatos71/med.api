"""add study plans

Revision ID: 0013
Revises: 0012
Create Date: 2026-06-02
"""

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS study_plans (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            exam_date DATE NOT NULL,
            status VARCHAR NOT NULL DEFAULT 'active',
            plan_json JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_study_plans_user_id ON study_plans (user_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS study_plans")
