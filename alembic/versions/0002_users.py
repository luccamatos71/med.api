"""create users table

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-23

"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE users (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            email VARCHAR NOT NULL,
            hashed_password VARCHAR NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE UNIQUE INDEX ix_users_email ON users (email)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS users")
