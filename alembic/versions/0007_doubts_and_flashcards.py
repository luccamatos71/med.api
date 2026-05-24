"""create doubts and flashcards tables

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-24
"""

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE flashcards (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            topic_id UUID NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
            material_id UUID REFERENCES materials(id) ON DELETE SET NULL,
            source VARCHAR NOT NULL DEFAULT 'manual',
            front TEXT NOT NULL,
            back TEXT NOT NULL,
            ai_approved_at TIMESTAMPTZ NULL,
            archived_at TIMESTAMPTZ NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX ix_flashcards_user_id ON flashcards (user_id)")
    op.execute("CREATE INDEX ix_flashcards_topic_id ON flashcards (topic_id)")

    op.execute(
        """
        CREATE TABLE doubts (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            topic_id UUID NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
            material_id UUID REFERENCES materials(id) ON DELETE SET NULL,
            question TEXT NOT NULL,
            ai_answer TEXT NULL,
            status VARCHAR NOT NULL DEFAULT 'pending',
            resolved_at TIMESTAMPTZ NULL,
            flashcard_id UUID REFERENCES flashcards(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX ix_doubts_user_id ON doubts (user_id)")
    op.execute("CREATE INDEX ix_doubts_topic_id ON doubts (topic_id)")
    op.execute("CREATE INDEX ix_doubts_status ON doubts (status)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS doubts CASCADE")
    op.execute("DROP TABLE IF EXISTS flashcards CASCADE")
