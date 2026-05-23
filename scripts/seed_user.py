"""
Create the initial user in the database.

Usage:
    SEED_EMAIL=lucca@example.com SEED_PASSWORD=yourpassword uv run python scripts/seed_user.py

Requires DATABASE_URL env var to be set (same as app).
"""
import asyncio
import os

import bcrypt
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.user import User


async def main() -> None:
    email = os.environ["SEED_EMAIL"]
    password = os.environ["SEED_PASSWORD"]

    engine = create_async_engine(os.environ["DATABASE_URL"])
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()

    async with session_factory() as session:
        user = User(email=email, hashed_password=hashed)
        session.add(user)
        await session.commit()
        await session.refresh(user)

    await engine.dispose()
    print(f"✅ User created: {email} (id={user.id})")


asyncio.run(main())
