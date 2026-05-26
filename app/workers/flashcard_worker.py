from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.flashcard import Flashcard
from app.models.material import Material
from app.models.material_chunk import MaterialChunk
from app.services.flashcard_generator import generate_flashcards_from_chunks


async def generate_flashcards(ctx, material_id: str) -> None:  # noqa: ARG001
    material: Material | None = None
    try:
        async with AsyncSessionLocal() as db:
            material_result = await db.execute(select(Material).where(Material.id == UUID(material_id)))
            material = material_result.scalar_one_or_none()
            if not material:
                raise ValueError(f"Material {material_id} not found")
            if material.processing_status != "ready":
                raise ValueError("Material is not ready for flashcard generation")

            chunks_result = await db.execute(
                select(MaterialChunk.content, MaterialChunk.chunk_metadata)
                .where(MaterialChunk.material_id == material.id, MaterialChunk.user_id == material.user_id)
                .order_by(MaterialChunk.created_at.asc())
            )
            chunks = [{"content": row.content, "metadata": row.chunk_metadata or {}} for row in chunks_result.all()]

        generated = await generate_flashcards_from_chunks(chunks)

        async with AsyncSessionLocal() as db:
            for item in generated:
                flashcard = Flashcard(
                    user_id=material.user_id,
                    topic_id=material.topic_id,
                    material_id=material.id,
                    source="ai_generated",
                    front=item.front,
                    back=item.back,
                    source_snippet=item.source_snippet,
                    page_number=item.page_number,
                    ai_approved_at=None,
                    archived_at=None,
                    created_at=datetime.now(timezone.utc),
                )
                db.add(flashcard)
            material_result = await db.execute(select(Material).where(Material.id == UUID(material_id)))
            material_to_update = material_result.scalar_one_or_none()
            if material_to_update:
                material_to_update.processing_error = None
            await db.commit()
    except Exception:
        async with AsyncSessionLocal() as db:
            material_result = await db.execute(select(Material).where(Material.id == UUID(material_id)))
            material_to_update = material_result.scalar_one_or_none()
            if material_to_update:
                material_to_update.processing_error = (
                    "Falha ao gerar flashcards automaticamente. Tente novamente."
                )
                await db.commit()
        raise
