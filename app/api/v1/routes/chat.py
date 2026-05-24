import json
import logging
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.rag import stream_chat
from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.chat_message import ChatMessage
from app.models.topic import Topic
from app.schemas.chat import ChatMessageResponse, ChatRequest

router = APIRouter(prefix="/topics", tags=["chat"])
logger = logging.getLogger(__name__)


async def _verify_topic_ownership(topic_id: UUID, user_id: str, db: AsyncSession) -> None:
    result = await db.execute(
        select(Topic).where(Topic.id == topic_id, Topic.user_id == user_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found")


@router.get("/{topic_id}/chat/messages", response_model=List[ChatMessageResponse])
async def get_chat_history(
    topic_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[ChatMessageResponse]:
    """Return the authenticated user's chat history for a topic."""
    user_id = current_user["user_id"]
    await _verify_topic_ownership(topic_id, user_id, db)

    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.topic_id == topic_id, ChatMessage.user_id == user_id)
        .order_by(ChatMessage.created_at.asc())
    )
    return [ChatMessageResponse.model_validate(message) for message in result.scalars().all()]


@router.post("/{topic_id}/chat/stream")
async def chat_stream(
    topic_id: UUID,
    body: ChatRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    user_id = current_user["user_id"]
    await _verify_topic_ownership(topic_id, user_id, db)
    if not settings.OPENAI_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OPENAI_API_KEY is not configured",
        )

    async def event_generator():
        try:
            async for event in stream_chat(
                db,
                topic_id=topic_id,
                user_id=user_id,
                question=body.question,
                selected_text=body.selected_text,
            ):
                yield event
        except Exception:
            logger.exception(
                "Chat stream failed",
                extra={"topic_id": str(topic_id), "user_id": user_id},
            )
            message = "O Tutor está temporariamente indisponível. Tente em alguns instantes."
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
