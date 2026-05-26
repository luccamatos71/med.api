from __future__ import annotations

import json
from typing import Any

from openai import AsyncOpenAI
from pydantic import BaseModel, ValidationError, field_validator

from app.core.config import settings

MODEL = "gpt-4o-mini"
MAX_CHUNKS = 12
MAX_CHARS_PER_CHUNK = 1200
MIN_FLASHCARDS = 5
MAX_FLASHCARDS = 15


class GeneratedFlashcard(BaseModel):
    front: str
    back: str
    source_snippet: str
    page_number: int | None = None

    @field_validator("front", "back", "source_snippet")
    @classmethod
    def text_non_empty(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("empty text")
        return text


class GeneratedFlashcardBatch(BaseModel):
    items: list[GeneratedFlashcard]


def _clean_json_payload(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    return text.strip()


def _chunks_to_context(chunks: list[dict[str, Any]]) -> str:
    selected = chunks[:MAX_CHUNKS]
    context: list[str] = []
    for chunk in selected:
        metadata = chunk.get("metadata") or {}
        page_number = metadata.get("page_number")
        page_label = f"p.{page_number}" if page_number else "p.?"
        content = (chunk.get("content") or "")[:MAX_CHARS_PER_CHUNK]
        context.append(f"[{page_label}] {content}")
    return "\n\n".join(context)


async def _repair_json_payload(client: AsyncOpenAI, raw: str) -> str:
    completion = await client.chat.completions.create(
        model=MODEL,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": (
                    "Conserte a saida e retorne APENAS JSON valido no formato "
                    '{"items":[{"front":"...","back":"...","source_snippet":"...","page_number":12}]}'
                ),
            },
            {"role": "user", "content": raw},
        ],
    )
    return completion.choices[0].message.content or ""


async def generate_flashcards_from_chunks(chunks: list[dict[str, Any]]) -> list[GeneratedFlashcard]:
    if not settings.OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not configured")
    if not chunks:
        raise RuntimeError("Material has no chunks to generate flashcards")

    prompt = (
        "Gere de 5 a 15 pares pergunta/resposta dos conceitos mais importantes. "
        "Para cada par, cite um trecho-fonte curto do contexto e o numero da pagina quando existir. "
        "Retorne APENAS JSON valido no formato: "
        '{"items":[{"front":"...","back":"...","source_snippet":"...","page_number":12}]}'
    )
    context = _chunks_to_context(chunks)

    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    completion = await client.chat.completions.create(
        model=MODEL,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": "Voce cria flashcards medicos objetivos em portugues."},
            {"role": "user", "content": f"{prompt}\n\nContexto:\n{context}"},
        ],
    )

    raw = completion.choices[0].message.content or ""
    payload = _clean_json_payload(raw)
    try:
        parsed = json.loads(payload)
        batch = GeneratedFlashcardBatch.model_validate(parsed)
    except (json.JSONDecodeError, ValidationError) as exc:
        repaired = await _repair_json_payload(client, raw)
        repaired_payload = _clean_json_payload(repaired)
        try:
            parsed = json.loads(repaired_payload)
            batch = GeneratedFlashcardBatch.model_validate(parsed)
        except (json.JSONDecodeError, ValidationError) as repair_exc:
            raise RuntimeError("Failed to parse flashcard generation output") from repair_exc

    if len(batch.items) < MIN_FLASHCARDS:
        raise RuntimeError("Generated fewer than 5 flashcards")
    if len(batch.items) > MAX_FLASHCARDS:
        return batch.items[:MAX_FLASHCARDS]
    return batch.items
