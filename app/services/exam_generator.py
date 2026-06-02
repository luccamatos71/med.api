from __future__ import annotations

import json
import random
from typing import Any

from openai import AsyncOpenAI
from pydantic import BaseModel, ValidationError, field_validator

from app.core.config import settings

MODEL = "gpt-4o-mini"
MAX_CHUNKS = 30
MAX_CHARS_PER_CHUNK = 1400


class GeneratedQuestion(BaseModel):
    stem: str
    options: list[str]
    correct_index: int
    explanation: str
    source_page: int | None = None

    @field_validator("options")
    @classmethod
    def four_options(cls, v: list[str]) -> list[str]:
        if len(v) < 2:
            raise ValueError("need at least 2 options")
        return v


class GeneratedExam(BaseModel):
    questions: list[GeneratedQuestion]


def _clean_json(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    return text.strip()


def _chunks_to_context(chunks: list[dict[str, Any]]) -> str:
    selected = chunks[:MAX_CHUNKS]
    parts: list[str] = []
    for chunk in selected:
        meta = chunk.get("metadata") or {}
        page = meta.get("page_number")
        label = f"p.{page}" if page else "p.?"
        parts.append(f"[{label}] {(chunk.get('content') or '')[:MAX_CHARS_PER_CHUNK]}")
    return "\n\n".join(parts)


SYSTEM_PROMPT = (
    "Você é uma professora de medicina que elabora questões de múltipla escolha de alta qualidade, "
    "no estilo de provas de residência, em português, baseadas EXCLUSIVAMENTE no material fornecido. "
    "Não invente fatos fora do material."
)


def _instructions(n: int) -> str:
    return (
        f"Crie {n} questões de múltipla escolha sobre o material. Retorne APENAS JSON válido:\n"
        '{"questions":[{"stem":"enunciado","options":["A","B","C","D"],'
        '"correct_index":0,"explanation":"por que a correta está certa e as outras erradas",'
        '"source_page":12}]}\n\n'
        "Regras:\n"
        "- Cada questão tem 4 alternativas plausíveis e exatamente uma correta (correct_index 0-3).\n"
        "- O enunciado deve cobrar entendimento, não decoreba trivial.\n"
        "- explanation curta e didática.\n"
        "- source_page = página do material que fundamenta a questão (ou null)."
    )


async def _repair(client: AsyncOpenAI, raw: str, n: int) -> str:
    completion = await client.chat.completions.create(
        model=MODEL,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": "Conserte e retorne APENAS JSON válido no schema de questões."},
            {"role": "user", "content": raw},
        ],
    )
    return completion.choices[0].message.content or ""


async def generate_exam_from_chunks(
    chunks: list[dict[str, Any]], num_questions: int
) -> list[dict[str, Any]]:
    if not settings.OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not configured")
    if not chunks:
        raise RuntimeError("No chunks to generate exam")

    context = _chunks_to_context(chunks)
    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    completion = await client.chat.completions.create(
        model=MODEL,
        temperature=0.4,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"{_instructions(num_questions)}\n\nMaterial:\n{context}"},
        ],
    )
    raw = completion.choices[0].message.content or ""
    try:
        parsed = GeneratedExam.model_validate(json.loads(_clean_json(raw)))
    except (json.JSONDecodeError, ValidationError):
        try:
            parsed = GeneratedExam.model_validate(json.loads(_clean_json(await _repair(client, raw, num_questions))))
        except (json.JSONDecodeError, ValidationError) as exc:
            raise RuntimeError("Failed to parse exam generation output") from exc

    questions: list[dict[str, Any]] = []
    for q in parsed.questions[:num_questions]:
        # Shuffle options so the correct answer isn't always in the model's slot.
        pairs = list(enumerate(q.options))
        random.shuffle(pairs)
        new_options = [text for _, text in pairs]
        new_correct = next(i for i, (orig, _) in enumerate(pairs) if orig == q.correct_index)
        questions.append(
            {
                "stem": q.stem,
                "options": new_options,
                "correct_index": new_correct,
                "explanation": q.explanation,
                "source": {"page": q.source_page} if q.source_page else None,
            }
        )
    if not questions:
        raise RuntimeError("No questions generated")
    return questions
