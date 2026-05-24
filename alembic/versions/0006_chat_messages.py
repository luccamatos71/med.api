"""create chat messages table

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-24

"""
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE chat_messages (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            topic_id UUID NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
            role VARCHAR NOT NULL,
            content TEXT NOT NULL,
            cited_chunks JSONB NOT NULL DEFAULT '[]'::jsonb,
            tokens_used INTEGER,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX ix_chat_messages_topic_id ON chat_messages (topic_id)")
    op.execute("CREATE INDEX ix_chat_messages_user_id ON chat_messages (user_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS chat_messages CASCADE")
