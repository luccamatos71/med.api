"""ARQ worker job for processing uploaded materials."""
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.material import Material
from app.models.material_chunk import MaterialChunk
from app.pipeline.chunker import chunk_pages, chunk_text
from app.pipeline.embedder import embed_chunks
from app.pipeline.pdf_parser import parse_pdf


def _download_from_storage(key: str) -> bytes:
    """Download a file from Supabase Storage via boto3 (S3-compatible).

    Uses a synchronous S3 get_object call — acceptable in a worker process.
    """
    from app.services.storage_service import s3
    from app.core.config import settings

    response = s3.get_object(Bucket=settings.STORAGE_BUCKET_NAME, Key=key)
    return response["Body"].read()


async def process_material(ctx, material_id: str) -> None:  # noqa: ARG001
    """ARQ job: process a material through the full pipeline.

    Steps:
    1. Load material from DB
    2. Set processing_status = 'processing'
    3. If type == 'pdf': download from storage, parse with pdf_parser
    4. Chunk text
    5. Generate embeddings
    6. Transactional insert: INSERT all MaterialChunks, then UPDATE material status=ready
    7. On any error: set processing_status='failed', processing_error=str(e), re-raise
    """
    # 1 & 2. Load material and mark as processing
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Material).where(Material.id == UUID(material_id))
        )
        material = result.scalar_one_or_none()
        if not material:
            raise ValueError(f"Material {material_id} not found")

        material_type = material.type
        material_file_key = material.file_key
        material_content = material.content
        user_id = material.user_id

        material.processing_status = "processing"
        await db.commit()

    try:
        # 3. Extract and chunk text
        if material_type == "pdf":
            if not material_file_key:
                raise ValueError("Material do tipo PDF não tem file_key")
            file_bytes = _download_from_storage(material_file_key)
            pages = parse_pdf(file_bytes)
            chunks = chunk_pages(pages)
        else:
            # text or note
            if not material_content:
                raise ValueError("Material do tipo texto não tem conteúdo")
            is_note = material_type == "note"
            chunks = chunk_text(material_content, is_note=is_note)

        # 4 & 5. Generate embeddings
        embeddings = await embed_chunks(chunks)

        # 6. Transactional insert of chunks + update material status
        async with AsyncSessionLocal() as db:
            chunk_objects = [
                MaterialChunk(
                    material_id=UUID(material_id),
                    user_id=user_id,
                    content=chunk_dict["content"],
                    embedding=embedding_vector,
                    metadata=chunk_dict["metadata"],
                )
                for chunk_dict, embedding_vector in zip(chunks, embeddings)
            ]
            db.add_all(chunk_objects)

            result = await db.execute(
                select(Material).where(Material.id == UUID(material_id))
            )
            material_obj = result.scalar_one()
            material_obj.processing_status = "ready"
            material_obj.processed_at = datetime.now(timezone.utc)
            material_obj.processing_error = None

            await db.commit()

    except Exception as exc:
        # 7. Mark as failed
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Material).where(Material.id == UUID(material_id))
            )
            material_obj = result.scalar_one_or_none()
            if material_obj:
                material_obj.processing_status = "failed"
                material_obj.processing_error = str(exc)
                await db.commit()
        raise
