"""create subjects table

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-23

"""
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE subjects (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name VARCHAR NOT NULL,
            color VARCHAR(7) NOT NULL,
            archived BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX ix_subjects_user_id ON subjects (user_id)")
    op.execute("CREATE UNIQUE INDEX ix_subjects_user_name ON subjects (user_id, LOWER(name))")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS subjects CASCADE")
