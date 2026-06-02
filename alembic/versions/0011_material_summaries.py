"""add material summaries

Revision ID: 0011
Revises: 0010
Create Date: 2026-06-02
"""

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS material_summaries (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            material_id UUID NOT NULL UNIQUE REFERENCES materials(id) ON DELETE CASCADE,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            summary_json JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_material_summaries_material_id ON material_summaries (material_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_material_summaries_user_id ON material_summaries (user_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS material_summaries")
