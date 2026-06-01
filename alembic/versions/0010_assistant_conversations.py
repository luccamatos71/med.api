"""add assistant conversations

Revision ID: 0010
Revises: 0009
Create Date: 2026-06-01
"""

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS conversations (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            title VARCHAR NULL,
            topic_id UUID NULL REFERENCES topics(id) ON DELETE SET NULL,
            material_id UUID NULL REFERENCES materials(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_conversations_user_id ON conversations (user_id)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_conversations_material_id ON conversations (material_id)"
    )

    # chat_messages: decouple from topic, attach to conversation.
    op.execute("ALTER TABLE chat_messages ALTER COLUMN topic_id DROP NOT NULL")
    op.execute("ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS conversation_id UUID NULL")
    op.execute(
        "ALTER TABLE chat_messages ADD CONSTRAINT fk_chat_messages_conversation_id "
        "FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_chat_messages_conversation_id "
        "ON chat_messages (conversation_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_chat_messages_conversation_id")
    op.execute("ALTER TABLE chat_messages DROP CONSTRAINT IF EXISTS fk_chat_messages_conversation_id")
    op.execute("ALTER TABLE chat_messages DROP COLUMN IF EXISTS conversation_id")
    op.execute("DROP TABLE IF EXISTS conversations")
