"""Materials API router — upload, CRUD, read-position endpoints."""
import uuid
from typing import List
from uuid import UUID

from arq import create_pool
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.material import Material
from app.models.material_read_position import MaterialReadPosition
from app.models.topic import Topic
from app.schemas.material import (
    MaterialCreate,
    MaterialResponse,
    ReadPositionResponse,
    ReadPositionUpdate,
)
from app.services.storage_service import upload_file
from app.workers.arq_settings import REDIS_SETTINGS

router = APIRouter(prefix="/materials", tags=["materials"])


async def _get_material_or_404(material_id: UUID, user_id: str, db: AsyncSession) -> Material:
    result = await db.execute(
        select(Material).where(Material.id == material_id, Material.user_id == user_id)
    )
    material = result.scalar_one_or_none()
    if not material:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Material not found")
    return material


async def _verify_topic_ownership(topic_id: UUID, user_id: str, db: AsyncSession) -> None:
    result = await db.execute(
        select(Topic).where(Topic.id == topic_id, Topic.user_id == user_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found")


async def _enqueue_process(material_id: UUID) -> None:
    """Enqueue the process_material ARQ job."""
    redis = await create_pool(REDIS_SETTINGS)
    await redis.enqueue_job("process_material", str(material_id))
    await redis.aclose()


# ---------------------------------------------------------------------------
# Upload endpoints
# ---------------------------------------------------------------------------


@router.post("/upload", response_model=MaterialResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_pdf(
    topic_id: UUID = Form(...),
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MaterialResponse:
    """Upload a PDF file for processing."""
    await _verify_topic_ownership(topic_id, current_user["user_id"], db)

    file_bytes = await file.read()
    file_size = len(file_bytes)

    # Build a unique storage key
    file_key = f"materials/{current_user['user_id']}/{uuid.uuid4()}/{file.filename}"
    await upload_file(file_bytes, file_key, file.content_type or "application/pdf")

    material = Material(
        topic_id=topic_id,
        user_id=current_user["user_id"],
        type="pdf",
        title=file.filename or "Uploaded PDF",
        file_key=file_key,
        file_size_bytes=file_size,
        processing_status="pending",
    )
    db.add(material)
    await db.commit()
    await db.refresh(material)

    await _enqueue_process(material.id)

    return MaterialResponse.model_validate(material)


@router.post("/text", response_model=MaterialResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_text_material(
    body: MaterialCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MaterialResponse:
    """Create a text or note material."""
    await _verify_topic_ownership(body.topic_id, current_user["user_id"], db)

    material = Material(
        topic_id=body.topic_id,
        user_id=current_user["user_id"],
        type=body.type,
        title=body.title,
        content=body.content,
        processing_status="pending",
    )
    db.add(material)
    await db.commit()
    await db.refresh(material)

    await _enqueue_process(material.id)

    return MaterialResponse.model_validate(material)


# ---------------------------------------------------------------------------
# CRUD endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=List[MaterialResponse])
async def list_materials(
    topic_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[MaterialResponse]:
    """List all materials for a topic."""
    await _verify_topic_ownership(topic_id, current_user["user_id"], db)

    result = await db.execute(
        select(Material)
        .where(Material.topic_id == topic_id, Material.user_id == current_user["user_id"])
        .order_by(Material.created_at)
    )
    materials = result.scalars().all()
    return [MaterialResponse.model_validate(m) for m in materials]


@router.get("/{material_id}", response_model=MaterialResponse)
async def get_material(
    material_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MaterialResponse:
    """Get a single material (useful for polling processing status)."""
    material = await _get_material_or_404(material_id, current_user["user_id"], db)
    return MaterialResponse.model_validate(material)


@router.post("/{material_id}/retry", response_model=MaterialResponse)
async def retry_material(
    material_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MaterialResponse:
    """Reset a failed material to pending and re-enqueue the processing job."""
    material = await _get_material_or_404(material_id, current_user["user_id"], db)

    if material.processing_status not in ("failed", "pending"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only failed or pending materials can be retried",
        )

    material.processing_status = "pending"
    material.processing_error = None
    await db.commit()
    await db.refresh(material)

    await _enqueue_process(material.id)

    return MaterialResponse.model_validate(material)


# ---------------------------------------------------------------------------
# Read position endpoints
# ---------------------------------------------------------------------------


@router.get("/{material_id}/read-position", response_model=ReadPositionResponse)
async def get_read_position(
    material_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ReadPositionResponse:
    """Get the read position for a material."""
    # Verify material access
    await _get_material_or_404(material_id, current_user["user_id"], db)

    result = await db.execute(
        select(MaterialReadPosition).where(
            MaterialReadPosition.material_id == material_id,
            MaterialReadPosition.user_id == current_user["user_id"],
        )
    )
    position = result.scalar_one_or_none()
    if not position:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Read position not found")
    return ReadPositionResponse.model_validate(position)


@router.patch("/{material_id}/read-position", response_model=ReadPositionResponse)
async def upsert_read_position(
    material_id: UUID,
    body: ReadPositionUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ReadPositionResponse:
    """Upsert the read position for a material."""
    # Verify material access
    await _get_material_or_404(material_id, current_user["user_id"], db)

    result = await db.execute(
        select(MaterialReadPosition).where(
            MaterialReadPosition.material_id == material_id,
            MaterialReadPosition.user_id == current_user["user_id"],
        )
    )
    position = result.scalar_one_or_none()

    if position:
        position.position_data = body.position_data
        from datetime import datetime, timezone
        position.updated_at = datetime.now(timezone.utc)
    else:
        position = MaterialReadPosition(
            material_id=material_id,
            user_id=current_user["user_id"],
            position_data=body.position_data,
        )
        db.add(position)

    await db.commit()
    await db.refresh(position)
    return ReadPositionResponse.model_validate(position)
