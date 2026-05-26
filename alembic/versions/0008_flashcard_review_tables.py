"""create flashcard review state and history tables

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-26
"""

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE flashcard_reviews (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            flashcard_id UUID NOT NULL REFERENCES flashcards(id) ON DELETE CASCADE,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            stability DOUBLE PRECISION NULL,
            difficulty DOUBLE PRECISION NULL,
            elapsed_days INTEGER NOT NULL DEFAULT 0,
            scheduled_days INTEGER NOT NULL DEFAULT 0,
            reps INTEGER NOT NULL DEFAULT 0,
            lapses INTEGER NOT NULL DEFAULT 0,
            state VARCHAR NOT NULL DEFAULT 'new'
                CHECK (state IN ('new', 'learning', 'review', 'relearning')),
            last_review TIMESTAMPTZ NULL,
            due_date TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX ix_flashcard_reviews_flashcard_id "
        "ON flashcard_reviews (flashcard_id)"
    )

    op.execute(
        """
        CREATE TABLE review_logs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            flashcard_id UUID NOT NULL REFERENCES flashcards(id) ON DELETE CASCADE,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            rating VARCHAR NOT NULL CHECK (rating IN ('again', 'hard', 'good', 'easy')),
            review_time TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            stability_before DOUBLE PRECISION NULL,
            stability_after DOUBLE PRECISION NULL
        )
        """
    )
    op.execute("CREATE INDEX ix_review_logs_flashcard_id ON review_logs (flashcard_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS review_logs CASCADE")
    op.execute("DROP TABLE IF EXISTS flashcard_reviews CASCADE")
