"""add flashcard source metadata fields

Revision ID: 0009
Revises: 0008
Create Date: 2026-05-26
"""

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE flashcards ADD COLUMN IF NOT EXISTS doubt_id UUID NULL")
    op.execute(
        "ALTER TABLE flashcards ADD CONSTRAINT fk_flashcards_doubt_id "
        "FOREIGN KEY (doubt_id) REFERENCES doubts(id) ON DELETE SET NULL"
    )
    op.execute("ALTER TABLE flashcards ADD COLUMN IF NOT EXISTS source_snippet TEXT NULL")
    op.execute("ALTER TABLE flashcards ADD COLUMN IF NOT EXISTS page_number INTEGER NULL")
    op.execute(
        "ALTER TABLE flashcards ADD CONSTRAINT ck_flashcards_source "
        "CHECK (source IN ('ai_generated', 'manual', 'from_doubt'))"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE flashcards DROP CONSTRAINT IF EXISTS ck_flashcards_source")
    op.execute("ALTER TABLE flashcards DROP COLUMN IF EXISTS page_number")
    op.execute("ALTER TABLE flashcards DROP COLUMN IF EXISTS source_snippet")
    op.execute("ALTER TABLE flashcards DROP CONSTRAINT IF EXISTS fk_flashcards_doubt_id")
    op.execute("ALTER TABLE flashcards DROP COLUMN IF EXISTS doubt_id")
