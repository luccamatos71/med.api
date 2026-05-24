import json
import logging
from datetime import datetime, timezone
from typing import Any, AsyncIterator
from uuid import UUID

from openai import APIError, APIStatusError, AsyncOpenAI
from sqlalchemy import delete, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.chat_message import ChatMessage
from app.models.material import Material
from app.models.material_chunk import MaterialChunk
from app.models.topic import Topic
from app.pipeline.embedder import embed_text

CHAT_MODEL = "gpt-4o"
SUMMARY_MODEL = "gpt-4o-mini"
K_RESULTS = 6
SIMILARITY_THRESHOLD = 0.7
MAX_HISTORY_MESSAGES = 20
SUMMARY_TRIGGER_MESSAGES = 30
logger = logging.getLogger(__name__)


def _sse(data: dict[str, Any]) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _topic_material_ids(db: AsyncSession, topic_id: UUID, user_id: str) -> list[UUID]:
    subtopics_res = await db.execute(
        select(Topic.id).where(Topic.parent_topic_id == topic_id, Topic.user_id == user_id)
    )
    subtopic_ids = [row[0] for row in subtopics_res.all()]
    topic_ids = [topic_id, *subtopic_ids]
    materials_res = await db.execute(
        select(Material.id).where(
            Material.topic_id.in_(topic_ids),
            Material.user_id == user_id,
            Material.processing_status == "ready",
        )
    )
    return [row[0] for row in materials_res.all()]


async def _recent_history(
    db: AsyncSession, topic_id: UUID, user_id: str, limit: int = MAX_HISTORY_MESSAGES
) -> list[ChatMessage]:
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.topic_id == topic_id, ChatMessage.user_id == user_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(limit)
    )
    messages = list(result.scalars().all())
    messages.reverse()
    return messages


async def _search_chunks(
    db: AsyncSession,
    query_embedding: list[float],
    material_ids: list[UUID],
    user_id: str,
    k: int = K_RESULTS,
    threshold: float = SIMILARITY_THRESHOLD,
) -> list[dict[str, Any]]:
    if not material_ids:
        return []

    distance_expr = MaterialChunk.embedding.cosine_distance(query_embedding)
    similarity_expr = (literal(1.0) - distance_expr).label("similarity")
    stmt = (
        select(
            MaterialChunk.id,
            MaterialChunk.content,
            MaterialChunk.chunk_metadata,
            Material.title.label("material_title"),
            similarity_expr,
        )
        .join(Material, Material.id == MaterialChunk.material_id)
        .where(
            MaterialChunk.material_id.in_(material_ids),
            MaterialChunk.user_id == user_id,
            MaterialChunk.embedding.is_not(None),
            similarity_expr >= threshold,
        )
        .order_by(distance_expr.asc())
        .limit(k)
    )
    result = await db.execute(stmt)
    rows = []
    for row in result.all():
        rows.append(
            {
                "id": row.id,
                "content": row.content,
                "metadata": row.chunk_metadata or {},
                "material_title": row.material_title,
                "similarity": float(row.similarity) if row.similarity is not None else 0.0,
            }
        )
    return rows


def _build_messages(
    question: str,
    chunks: list[dict[str, Any]],
    history: list[ChatMessage],
    selected_text: str | None = None,
) -> list[dict[str, str]]:
    system_text = (
        "Você é um tutor médico sênior para estudo. "
        "Responda de forma clara e objetiva com base nos materiais fornecidos. "
        "Se não houver base suficiente nos materiais, diga explicitamente."
    )
    context_parts: list[str] = []
    for chunk in chunks:
        meta = chunk.get("metadata") or {}
        page = meta.get("page_number")
        page_suffix = f" · p.{page}" if page else ""
        context_parts.append(f"[{chunk['material_title']}{page_suffix}]\n{chunk['content']}")
    context_text = "\n\n---\n\n".join(context_parts)

    messages: list[dict[str, str]] = [{"role": "system", "content": system_text}]
    if context_text:
        messages.append({"role": "system", "content": f"Materiais do estudante:\n\n{context_text}"})

    for msg in history:
        if msg.role in ("user", "assistant"):
            messages.append({"role": msg.role, "content": msg.content})
        elif msg.role == "system":
            messages.append(
                {"role": "system", "content": f"Resumo de conversas anteriores: {msg.content}"}
            )

    user_content = question
    if selected_text:
        user_content = f'Trecho selecionado: "{selected_text}"\n\nPergunta: {question}'
    messages.append({"role": "user", "content": user_content})
    return messages


async def _save_messages(
    db: AsyncSession,
    *,
    topic_id: UUID,
    user_id: str,
    question: str,
    answer: str,
    cited_chunks: list[dict[str, Any]],
    tokens_used: int | None = None,
) -> ChatMessage:
    user_msg = ChatMessage(
        user_id=user_id,
        topic_id=topic_id,
        role="user",
        content=question,
        cited_chunks=[],
    )
    assistant_msg = ChatMessage(
        user_id=user_id,
        topic_id=topic_id,
        role="assistant",
        content=answer,
        cited_chunks=cited_chunks,
        tokens_used=tokens_used,
    )
    db.add(user_msg)
    db.add(assistant_msg)
    await db.commit()
    await db.refresh(assistant_msg)
    return assistant_msg


async def _maybe_summarize_history(db: AsyncSession, topic_id: UUID, user_id: str) -> None:
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.topic_id == topic_id, ChatMessage.user_id == user_id)
        .order_by(ChatMessage.created_at.asc())
    )
    messages = list(result.scalars().all())
    if len(messages) <= SUMMARY_TRIGGER_MESSAGES:
        return

    to_summarize = messages[:-MAX_HISTORY_MESSAGES]
    if not to_summarize:
        return

    if not settings.OPENAI_API_KEY:
        return

    conversation = "\n".join([f"{m.role}: {m.content}" for m in to_summarize])
    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    try:
        summary_resp = await client.chat.completions.create(
            model=SUMMARY_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Resuma em até 5 frases os tópicos discutidos, dúvidas levantadas e conclusões importantes."
                    ),
                },
                {"role": "user", "content": conversation},
            ],
        )
    except Exception:
        logger.exception(
            "Failed to summarize chat history",
            extra={"topic_id": str(topic_id), "user_id": user_id},
        )
        return
    summary = (summary_resp.choices[0].message.content or "").strip()
    if not summary:
        return

    old_ids = [m.id for m in to_summarize]
    await db.execute(delete(ChatMessage).where(ChatMessage.id.in_(old_ids)))
    db.add(
        ChatMessage(
            user_id=user_id,
            topic_id=topic_id,
            role="system",
            content=summary,
            cited_chunks=[],
            created_at=datetime.now(timezone.utc),
        )
    )
    await db.commit()


async def stream_chat(
    db: AsyncSession,
    *,
    topic_id: UUID,
    user_id: str,
    question: str,
    selected_text: str | None = None,
) -> AsyncIterator[str]:
    query_text = f"{selected_text}\n\n{question}" if selected_text else question
    embedding = await embed_text(query_text)
    material_ids = await _topic_material_ids(db, topic_id, user_id)
    chunks = await _search_chunks(db, embedding, material_ids, user_id)

    fallback = (
        "Não encontrei informação suficiente nos seus materiais sobre isso. "
        "Tente adicionar um material relevante."
    )
    if len(chunks) < 2:
        logger.info(
            "RAG fallback due to insufficient chunks",
            extra={"topic_id": str(topic_id), "user_id": user_id, "chunks_found": len(chunks)},
        )
        assistant = await _save_messages(
            db,
            topic_id=topic_id,
            user_id=user_id,
            question=question,
            answer=fallback,
            cited_chunks=[],
            tokens_used=None,
        )
        yield _sse({"type": "token", "content": fallback})
        yield _sse({"type": "source", "chunks": []})
        yield _sse({"type": "done", "message_id": str(assistant.id)})
        return

    history = await _recent_history(db, topic_id, user_id)
    messages = _build_messages(question, chunks, history, selected_text)

    if not settings.OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not configured")

    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    stream = await client.chat.completions.create(
        model=CHAT_MODEL,
        messages=messages,
        stream=True,
    )

    full_response = ""
    completion_tokens: int | None = None
    try:
        async for chunk in stream:
            choice = chunk.choices[0]
            delta = choice.delta.content or ""
            if delta:
                full_response += delta
                yield _sse({"type": "token", "content": delta})
            if getattr(chunk, "usage", None):
                completion_tokens = getattr(chunk.usage, "total_tokens", None)
    except APIStatusError as exc:
        logger.exception(
            "OpenAI APIStatusError while streaming chat",
            extra={"topic_id": str(topic_id), "user_id": user_id, "status_code": exc.status_code},
        )
        if exc.status_code == 503:
            raise
        raise RuntimeError("OpenAI temporarily unavailable") from exc
    except APIError as exc:
        logger.exception(
            "OpenAI APIError while streaming chat",
            extra={"topic_id": str(topic_id), "user_id": user_id},
        )
        raise RuntimeError("OpenAI temporarily unavailable") from exc

    cited_chunks: list[dict[str, Any]] = []
    for chunk in chunks:
        meta = chunk.get("metadata") or {}
        cited_chunks.append(
            {
                "chunk_id": str(chunk["id"]),
                "material_title": chunk["material_title"],
                "page_number": meta.get("page_number"),
                "snippet": chunk["content"][:180],
            }
        )
    yield _sse({"type": "source", "chunks": cited_chunks})

    assistant = await _save_messages(
        db,
        topic_id=topic_id,
        user_id=user_id,
        question=question,
        answer=full_response,
        cited_chunks=cited_chunks,
        tokens_used=completion_tokens,
    )
    await _maybe_summarize_history(db, topic_id, user_id)
    yield _sse({"type": "done", "message_id": str(assistant.id)})
