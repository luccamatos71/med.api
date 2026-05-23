"""create materials tables

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-23

"""
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE materials (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            topic_id UUID NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            type VARCHAR NOT NULL,
            title VARCHAR NOT NULL,
            content TEXT,
            file_key VARCHAR,
            file_size_bytes INTEGER,
            processing_status VARCHAR NOT NULL DEFAULT 'pending',
            processing_error VARCHAR,
            processed_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX ix_materials_topic_id ON materials (topic_id)")
    op.execute("CREATE INDEX ix_materials_user_id ON materials (user_id)")

    op.execute("""
        CREATE TABLE material_chunks (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            material_id UUID NOT NULL REFERENCES materials(id) ON DELETE CASCADE,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            content TEXT NOT NULL,
            embedding vector(1536),
            metadata JSONB NOT NULL DEFAULT '{}',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX ix_material_chunks_material_id ON material_chunks (material_id)")
    op.execute("CREATE INDEX ix_material_chunks_user_id ON material_chunks (user_id)")

    op.execute("""
        CREATE TABLE material_read_position (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            material_id UUID NOT NULL REFERENCES materials(id) ON DELETE CASCADE,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            position_data JSONB NOT NULL DEFAULT '{}',
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE UNIQUE INDEX ix_material_read_position_material_user "
        "ON material_read_position (material_id, user_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS material_read_position CASCADE")
    op.execute("DROP TABLE IF EXISTS material_chunks CASCADE")
    op.execute("DROP TABLE IF EXISTS materials CASCADE")
