import json
import logging
from datetime import datetime, timezone
from typing import Any, AsyncIterator
from uuid import UUID

from openai import APIError, APIStatusError, AsyncOpenAI
from sqlalchemy import case, delete, literal, select
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
MAX_HISTORY_CONTEXT_BYTES = 4000
NOTE_RELEVANCE_WEIGHT = 0.7
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
    summary_result = await db.execute(
        select(ChatMessage)
        .where(
            ChatMessage.topic_id == topic_id,
            ChatMessage.user_id == user_id,
            ChatMessage.role == "system",
        )
        .order_by(ChatMessage.created_at.desc())
        .limit(1)
    )
    summary = summary_result.scalar_one_or_none()
    result = await db.execute(
        select(ChatMessage)
        .where(
            ChatMessage.topic_id == topic_id,
            ChatMessage.user_id == user_id,
            ChatMessage.role != "system",
        )
        .order_by(ChatMessage.created_at.desc())
        .limit(limit)
    )
    messages = list(result.scalars().all())
    messages.reverse()
    if summary:
        messages.insert(0, summary)
    return _trim_history_to_budget(messages)


def _trim_history_to_budget(messages: list[ChatMessage]) -> list[ChatMessage]:
    """Keep latest chat context under a conservative 4,000-token ceiling."""
    summary = next((message for message in reversed(messages) if message.role == "system"), None)
    budget = MAX_HISTORY_CONTEXT_BYTES
    selected: list[ChatMessage] = []

    if summary:
        summary_size = len(summary.content.encode("utf-8"))
        if summary_size <= budget:
            selected.append(summary)
            budget -= summary_size

    recent: list[ChatMessage] = []
    for message in reversed(messages):
        if message.role == "system":
            continue
        size = len(message.content.encode("utf-8"))
        if size <= budget:
            recent.append(message)
            budget -= size

    selected.extend(reversed(recent))
    return selected


async def _search_chunks(
    db: AsyncSession,
    query_embedding: list[float],
    material_ids: list[UUID],
    user_id: str,
    active_material_id: UUID | None = None,
    k: int = K_RESULTS,
    threshold: float = SIMILARITY_THRESHOLD,
) -> list[dict[str, Any]]:
    if not material_ids:
        return []

    distance_expr = MaterialChunk.embedding.cosine_distance(query_embedding)
    similarity_expr = literal(1.0) - distance_expr
    relevance_expr = (
        similarity_expr
        * case((Material.type == "note", NOTE_RELEVANCE_WEIGHT), else_=1.0)
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
            priority_expr,
            relevance_expr,
        )
        .join(Material, Material.id == MaterialChunk.material_id)
        .where(
            MaterialChunk.material_id.in_(material_ids),
            MaterialChunk.user_id == user_id,
            MaterialChunk.embedding.is_not(None),
            similarity_expr >= threshold,
        )
        .order_by(priority_expr.desc(), relevance_expr.desc())
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
                "material_id": row.material_id,
                "topic_id": row.topic_id,
                "similarity": float(row.relevance) if row.relevance is not None else 0.0,
            }
        )
    return rows


def _build_messages(
    question: str,
    chunks: list[dict[str, Any]],
    history: list[ChatMessage],
    selected_text: str | None = None,
    general_knowledge: bool = False,
) -> list[dict[str, str]]:
    system_text = (
        "Você é um tutor de estudos em saúde que explica em português natural, próximo e rigoroso. "
        "Comece pela lógica principal da dúvida e responda primeiro ao que foi perguntado. "
        "Quando ajudar, use expressões naturais como 'Pensa assim...', 'A confusão está aqui...' ou "
        "'Grava assim...', analogias simples e sequências com setas. "
        "Se a estudante estiver parcialmente certa, corrija sem invalidar o raciocínio. "
        "Evite aula longa, tom de manual e estruturas fixas com subtítulos obrigatórios. "
        "Use os materiais recuperados e o trecho selecionado (quando houver) como base prioritária. "
        "Nunca afirme que um material diz algo, nunca cite página e nunca declare fonte se isso não estiver "
        "explicitamente no contexto recuperado desta conversa. "
        "Não escreva uma seção de fontes: a aplicação adiciona fontes reais separadamente."
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
    elif general_knowledge:
        messages.append(
            {
                "role": "system",
                "content": (
                    "Nenhum trecho relevante foi recuperado dos materiais deste tópico. "
                    "Responda usando conhecimento geral confiável, sem alegar grounding em material, "
                    "sem mencionar fontes ou páginas e sem repetir o aviso de ausência de fonte, "
                    "pois a aplicação já o exibiu."
                ),
            }
        )

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
    active_material_id: UUID | None = None,
) -> AsyncIterator[str]:
    query_text = f"{selected_text}\n\n{question}" if selected_text else question
    embedding = await embed_text(query_text)
    material_ids = await _topic_material_ids(db, topic_id, user_id)
    chunks = await _search_chunks(
        db,
        embedding,
        material_ids,
        user_id,
        active_material_id=active_material_id,
    )

    fallback = (
        "Não encontrei isso diretamente nos materiais deste tópico, então vou te explicar pela lógica geral."
    )
    general_knowledge = not chunks and not selected_text
    if general_knowledge:
        logger.info(
            "RAG answering with general knowledge due to no recovered chunks",
            extra={"topic_id": str(topic_id), "user_id": user_id},
        )

    history = await _recent_history(db, topic_id, user_id)
    messages = _build_messages(
        question,
        chunks,
        history,
        selected_text,
        general_knowledge=general_knowledge,
    )

    if not settings.OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not configured")

    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    stream = await client.chat.completions.create(
        model=CHAT_MODEL,
        messages=messages,
        stream=True,
    )

    full_response = ""
    if general_knowledge:
        full_response = f"{fallback}\n\n"
        yield _sse({"type": "token", "content": full_response})
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
                "material_id": str(chunk["material_id"]),
                "topic_id": str(chunk["topic_id"]),
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
