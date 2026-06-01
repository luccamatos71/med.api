import json
import logging
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.assistant import stream_assistant
from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.chat_message import ChatMessage
from app.models.conversation import Conversation
from app.models.material import Material
from app.schemas.assistant import (
    AssistantChatRequest,
    AssistantMessageResponse,
    ConversationCreate,
    ConversationResponse,
)

router = APIRouter(prefix="/assistant", tags=["assistant"])
logger = logging.getLogger(__name__)


async def _get_conversation(conversation_id: UUID, user_id: str, db: AsyncSession) -> Conversation:
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id, Conversation.user_id == user_id
        )
    )
    conversation = result.scalar_one_or_none()
    if not conversation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    return conversation


@router.get("/conversations", response_model=List[ConversationResponse])
async def list_conversations(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[ConversationResponse]:
    user_id = current_user["user_id"]
    result = await db.execute(
        select(Conversation)
        .where(Conversation.user_id == user_id)
        .order_by(Conversation.updated_at.desc())
    )
    return [ConversationResponse.model_validate(c) for c in result.scalars().all()]


@router.post("/conversations", response_model=ConversationResponse)
async def create_conversation(
    body: ConversationCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationResponse:
    user_id = current_user["user_id"]
    conversation = Conversation(
        user_id=user_id,
        title=body.title,
        topic_id=body.topic_id,
        material_id=body.material_id,
    )
    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)
    return ConversationResponse.model_validate(conversation)


@router.post("/conversations/for-material/{material_id}", response_model=ConversationResponse)
async def get_or_create_material_conversation(
    material_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationResponse:
    """Return the existing conversation bound to this material, or create one.

    Used by the in-material chat panel so it always continues the same thread.
    """
    user_id = current_user["user_id"]
    material_res = await db.execute(
        select(Material).where(Material.id == material_id, Material.user_id == user_id)
    )
    material = material_res.scalar_one_or_none()
    if not material:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Material not found")

    existing = await db.execute(
        select(Conversation)
        .where(Conversation.user_id == user_id, Conversation.material_id == material_id)
        .order_by(Conversation.updated_at.desc())
        .limit(1)
    )
    conversation = existing.scalar_one_or_none()
    if conversation:
        return ConversationResponse.model_validate(conversation)

    conversation = Conversation(
        user_id=user_id,
        title=material.title,
        topic_id=material.topic_id,
        material_id=material_id,
    )
    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)
    return ConversationResponse.model_validate(conversation)


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=List[AssistantMessageResponse],
)
async def get_messages(
    conversation_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[AssistantMessageResponse]:
    user_id = current_user["user_id"]
    await _get_conversation(conversation_id, user_id, db)
    result = await db.execute(
        select(ChatMessage)
        .where(
            ChatMessage.conversation_id == conversation_id,
            ChatMessage.user_id == user_id,
            ChatMessage.role != "system",
        )
        .order_by(ChatMessage.created_at.asc())
    )
    return [AssistantMessageResponse.model_validate(m) for m in result.scalars().all()]


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    user_id = current_user["user_id"]
    await _get_conversation(conversation_id, user_id, db)
    await db.execute(delete(Conversation).where(Conversation.id == conversation_id))
    await db.commit()


@router.post("/conversations/{conversation_id}/stream")
async def chat_stream(
    conversation_id: UUID,
    body: AssistantChatRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    user_id = current_user["user_id"]
    conversation = await _get_conversation(conversation_id, user_id, db)
    if not settings.OPENAI_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OPENAI_API_KEY is not configured",
        )

    async def event_generator():
        try:
            async for event in stream_assistant(
                db,
                conversation=conversation,
                user_id=user_id,
                question=body.question,
                active_material_id=body.active_material_id,
                selected_text=body.selected_text,
            ):
                yield event
        except Exception:
            logger.exception(
                "Assistant stream failed",
                extra={"conversation_id": str(conversation_id), "user_id": user_id},
            )
            message = "O assistente está temporariamente indisponível. Tente em alguns instantes."
            yield f"data: {json.dumps({'type': 'error', 'message': message}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
