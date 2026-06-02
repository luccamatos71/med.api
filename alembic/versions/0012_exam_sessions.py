"""add exam sessions

Revision ID: 0012
Revises: 0011
Create Date: 2026-06-02
"""

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS exam_sessions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            scope_type VARCHAR NOT NULL,
            scope_id UUID NOT NULL,
            scope_name VARCHAR NULL,
            num_questions INTEGER NOT NULL DEFAULT 10,
            status VARCHAR NOT NULL DEFAULT 'in_progress',
            score DOUBLE PRECISION NULL,
            duration_seconds INTEGER NULL,
            questions_json JSONB NOT NULL,
            answers_json JSONB NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            finished_at TIMESTAMPTZ NULL
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_exam_sessions_user_id ON exam_sessions (user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_exam_sessions_scope_id ON exam_sessions (scope_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS exam_sessions")
