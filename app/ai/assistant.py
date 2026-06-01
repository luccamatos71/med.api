"""Conversational assistant engine (ChatGPT-style, hybrid RAG).

This is the single brain behind both the dedicated `/assistente` tab and the
in-material chat panel. It answers general questions naturally; when the user's
own materials are relevant it grounds the answer in them and returns real
sources. Conversations are decoupled from topics — an optional material context
only re-prioritises retrieval.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, AsyncIterator
from uuid import UUID

from openai import APIError, APIStatusError, AsyncOpenAI
from sqlalchemy import case, literal, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.chat_message import ChatMessage
from app.models.conversation import Conversation
from app.models.material import Material
from app.models.material_chunk import MaterialChunk
from app.models.topic import Topic
from app.pipeline.embedder import embed_text

CHAT_MODEL = "gpt-4o"
TITLE_MODEL = "gpt-4o-mini"
K_RESULTS = 6
SIMILARITY_THRESHOLD = 0.72
MAX_HISTORY_MESSAGES = 20
MAX_HISTORY_CONTEXT_BYTES = 6000
NOTE_RELEVANCE_WEIGHT = 0.7
logger = logging.getLogger(__name__)


def _sse(data: dict[str, Any]) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


SYSTEM_PROMPT = (
    "Você é o assistente de estudos da .med — inteligente, direto e conversacional, "
    "como um ChatGPT focado em ajudar uma estudante de medicina. "
    "Entenda exatamente o que ela perguntou e responda de forma natural e completa, "
    "sem tom de manual nem estrutura rígida obrigatória. "
    "Use markdown quando ajudar a clareza: **negrito** para o essencial, listas, tabelas "
    "para comparações, blocos de código quando fizer sentido, e setas (→) para sequências. "
    "Responda no idioma da pergunta (padrão: português). "
    "Você tem conhecimento geral amplo: responda qualquer assunto, não apenas o que está nos materiais. "
    "Quando houver trechos dos materiais da estudante no contexto, use-os como base prioritária e "
    "explique com base neles. "
    "Nunca invente que um material diz algo, nunca cite página e nunca declare fonte se isso não "
    "estiver explicitamente no contexto recuperado. Não escreva uma seção de fontes — a aplicação "
    "anexa as fontes reais separadamente."
)


async def _user_material_ids(
    db: AsyncSession, user_id: str, material_id: UUID | None
) -> list[UUID] | None:
    """Materials to search. ``None`` = search all ready materials for the user."""
    if material_id is not None:
        return [material_id]
    return None


async def _search_chunks(
    db: AsyncSession,
    query_embedding: list[float],
    user_id: str,
    material_ids: list[UUID] | None,
    active_material_id: UUID | None = None,
    k: int = K_RESULTS,
    threshold: float = SIMILARITY_THRESHOLD,
) -> list[dict[str, Any]]:
    distance_expr = MaterialChunk.embedding.cosine_distance(query_embedding)
    similarity_expr = literal(1.0) - distance_expr
    relevance_expr = (
        similarity_expr * case((Material.type == "note", NOTE_RELEVANCE_WEIGHT), else_=1.0)
    ).label("relevance")
    priority_expr = (
        case((Material.id == active_material_id, 1), else_=0).label("active_material_priority")
        if active_material_id
        else literal(0).label("active_material_priority")
    )
    stmt = (
        select(
            MaterialChunk.id,
            MaterialChunk.content,
            MaterialChunk.chunk_metadata,
            Material.title.label("material_title"),
            Material.id.label("material_id"),
            Material.topic_id.label("topic_id"),
            Topic.subject_id.label("subject_id"),
            priority_expr,
            relevance_expr,
        )
        .join(Material, Material.id == MaterialChunk.material_id)
        .join(Topic, Topic.id == Material.topic_id)
        .where(
            MaterialChunk.user_id == user_id,
            MaterialChunk.embedding.is_not(None),
            Material.processing_status == "ready",
            similarity_expr >= threshold,
        )
        .order_by(priority_expr.desc(), relevance_expr.desc())
        .limit(k)
    )
    if material_ids is not None:
        if not material_ids:
            return []
        stmt = stmt.where(MaterialChunk.material_id.in_(material_ids))

    result = await db.execute(stmt)
    rows = []
    for row in result.all():
        rows.append(
            {
                "id": row.id,
                "content": row.content,
                "metadata": row.chunk_metadata or {},
                "material_title": row.material_title,
                "material_id": row.material_id,
                "topic_id": row.topic_id,
                "subject_id": row.subject_id,
            }
        )
    return rows


async def _conversation_history(
    db: AsyncSession, conversation_id: UUID, user_id: str
) -> list[ChatMessage]:
    result = await db.execute(
        select(ChatMessage)
        .where(
            ChatMessage.conversation_id == conversation_id,
            ChatMessage.user_id == user_id,
        )
        .order_by(ChatMessage.created_at.desc())
        .limit(MAX_HISTORY_MESSAGES)
    )
    messages = list(result.scalars().all())
    messages.reverse()

    budget = MAX_HISTORY_CONTEXT_BYTES
    selected: list[ChatMessage] = []
    for message in reversed(messages):
        size = len(message.content.encode("utf-8"))
        if size > budget:
            break
        selected.append(message)
        budget -= size
    selected.reverse()
    return selected


def _build_messages(
    question: str,
    chunks: list[dict[str, Any]],
    history: list[ChatMessage],
    selected_text: str | None,
) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]

    if chunks:
        context_parts: list[str] = []
        for chunk in chunks:
            meta = chunk.get("metadata") or {}
            page = meta.get("page_number")
            page_suffix = f" · p.{page}" if page else ""
            context_parts.append(f"[{chunk['material_title']}{page_suffix}]\n{chunk['content']}")
        context_text = "\n\n---\n\n".join(context_parts)
        messages.append(
            {"role": "system", "content": f"Trechos dos materiais da estudante:\n\n{context_text}"}
        )

    for msg in history:
        if msg.role in ("user", "assistant"):
            messages.append({"role": msg.role, "content": msg.content})

    user_content = question
    if selected_text:
        user_content = f'Trecho selecionado: "{selected_text}"\n\nPergunta: {question}'
    messages.append({"role": "user", "content": user_content})
    return messages


async def _save_messages(
    db: AsyncSession,
    *,
    conversation_id: UUID,
    user_id: str,
    topic_id: UUID | None,
    question: str,
    answer: str,
    cited_chunks: list[dict[str, Any]],
    tokens_used: int | None,
) -> ChatMessage:
    user_msg = ChatMessage(
        user_id=user_id,
        conversation_id=conversation_id,
        topic_id=topic_id,
        role="user",
        content=question,
        cited_chunks=[],
    )
    assistant_msg = ChatMessage(
        user_id=user_id,
        conversation_id=conversation_id,
        topic_id=topic_id,
        role="assistant",
        content=answer,
        cited_chunks=cited_chunks,
        tokens_used=tokens_used,
    )
    db.add(user_msg)
    db.add(assistant_msg)
    await db.execute(
        update(Conversation)
        .where(Conversation.id == conversation_id)
        .values(updated_at=datetime.now(timezone.utc))
    )
    await db.commit()
    await db.refresh(assistant_msg)
    return assistant_msg


async def _maybe_set_title(
    db: AsyncSession, conversation: Conversation, question: str
) -> str | None:
    if conversation.title:
        return None
    title = question.strip().splitlines()[0][:60] if question.strip() else "Nova conversa"
    if settings.OPENAI_API_KEY:
        try:
            client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
            resp = await client.chat.completions.create(
                model=TITLE_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": "Gere um título curto (máx 6 palavras) para esta conversa. Só o título.",
                    },
                    {"role": "user", "content": question[:500]},
                ],
            )
            generated = (resp.choices[0].message.content or "").strip().strip('"')
            if generated:
                title = generated[:60]
        except Exception:
            logger.debug("Title generation failed; using fallback", exc_info=True)
    await db.execute(
        update(Conversation).where(Conversation.id == conversation.id).values(title=title)
    )
    await db.commit()
    return title


async def stream_assistant(
    db: AsyncSession,
    *,
    conversation: Conversation,
    user_id: str,
    question: str,
    active_material_id: UUID | None = None,
    selected_text: str | None = None,
) -> AsyncIterator[str]:
    if not settings.OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not configured")

    new_title = await _maybe_set_title(db, conversation, question)
    if new_title:
        yield _sse({"type": "title", "title": new_title})

    # Context material: explicit arg wins, else the conversation's bound material.
    context_material_id = active_material_id or conversation.material_id

    query_text = f"{selected_text}\n\n{question}" if selected_text else question
    embedding = await embed_text(query_text)
    material_ids = await _user_material_ids(db, user_id, context_material_id)
    chunks = await _search_chunks(
        db,
        embedding,
        user_id,
        material_ids,
        active_material_id=context_material_id,
    )

    history = await _conversation_history(db, conversation.id, user_id)
    messages = _build_messages(question, chunks, history, selected_text)

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
            "OpenAI APIStatusError while streaming assistant",
            extra={"conversation_id": str(conversation.id), "user_id": user_id},
        )
        if exc.status_code == 503:
            raise
        raise RuntimeError("OpenAI temporarily unavailable") from exc
    except APIError as exc:
        logger.exception(
            "OpenAI APIError while streaming assistant",
            extra={"conversation_id": str(conversation.id), "user_id": user_id},
        )
        raise RuntimeError("OpenAI temporarily unavailable") from exc

    cited_chunks: list[dict[str, Any]] = []
    for chunk in chunks:
        meta = chunk.get("metadata") or {}
        cited_chunks.append(
            {
                "chunk_id": str(chunk["id"]),
                "material_title": chunk["material_title"],
                "material_id": str(chunk["material_id"]),
                "topic_id": str(chunk["topic_id"]) if chunk["topic_id"] else None,
                "subject_id": str(chunk["subject_id"]) if chunk.get("subject_id") else None,
                "page_number": meta.get("page_number"),
                "snippet": chunk["content"][:180],
            }
        )
    yield _sse({"type": "source", "chunks": cited_chunks})

    assistant = await _save_messages(
        db,
        conversation_id=conversation.id,
        user_id=user_id,
        topic_id=conversation.topic_id,
        question=question,
        answer=full_response,
        cited_chunks=cited_chunks,
        tokens_used=completion_tokens,
    )
    yield _sse({"type": "done", "message_id": str(assistant.id)})
