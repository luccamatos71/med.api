"""create topics table

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-23

"""
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE topics (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            subject_id UUID NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            parent_topic_id UUID REFERENCES topics(id) ON DELETE CASCADE,
            name VARCHAR NOT NULL,
            position INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX ix_topics_subject_id ON topics (subject_id)")
    op.execute("CREATE INDEX ix_topics_parent_topic_id ON topics (parent_topic_id)")
    op.execute("CREATE INDEX ix_topics_user_id ON topics (user_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS topics CASCADE")
