from __future__ import annotations

import json
from typing import Any

from openai import AsyncOpenAI
from pydantic import ValidationError

from app.core.config import settings
from app.schemas.summary import SummaryContent

MODEL = "gpt-4o-mini"
MAX_CHUNKS = 30
MAX_CHARS_PER_CHUNK = 1500


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


SYSTEM_PROMPT = (
    "Você é uma tutora de medicina que cria resumos de estudo claros, bonitos e bem estruturados "
    "em português, a partir do material da estudante. Resuma com fidelidade ao conteúdo fornecido, "
    "sem inventar fatos que não estejam no material."
)

INSTRUCTIONS = (
    "Gere um resumo de estudo estruturado do material abaixo. Retorne APENAS JSON válido no formato:\n"
    "{\n"
    '  "title": "título curto do tema",\n'
    '  "tldr": "resumo de 2-3 frases do essencial",\n'
    '  "key_points": ["ponto-chave 1", "ponto-chave 2", "..."],\n'
    '  "sections": [{"heading": "subtema", "bullets": ["explicação concisa", "..."]}],\n'
    '  "glossary": [{"term": "termo", "definition": "definição curta"}],\n'
    '  "clinical_pearls": ["dica prática/pegadinha de prova", "..."],\n'
    '  "mindmap_markdown": "# Tema\\n## Subtema A\\n- conceito\\n## Subtema B\\n- conceito"\n'
    "}\n\n"
    "Regras:\n"
    "- 4 a 8 key_points; 3 a 6 sections com 2 a 5 bullets cada.\n"
    "- glossary com 4 a 10 termos importantes; clinical_pearls com 2 a 5 itens (pode ser [] se não houver).\n"
    "- mindmap_markdown: hierarquia em markdown (#, ##, ###, -) cobrindo o tema e seus ramos principais.\n"
    "- Linguagem objetiva, didática e fiel ao material."
)


async def _repair_json(client: AsyncOpenAI, raw: str) -> str:
    completion = await client.chat.completions.create(
        model=MODEL,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": "Conserte a saída e retorne APENAS JSON válido no schema de resumo solicitado.",
            },
            {"role": "user", "content": raw},
        ],
    )
    return completion.choices[0].message.content or ""


async def generate_summary_from_chunks(chunks: list[dict[str, Any]]) -> SummaryContent:
    if not settings.OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not configured")
    if not chunks:
        raise RuntimeError("Material has no chunks to summarize")

    context = _chunks_to_context(chunks)
    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    completion = await client.chat.completions.create(
        model=MODEL,
        temperature=0.2,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"{INSTRUCTIONS}\n\nMaterial:\n{context}"},
        ],
    )

    raw = completion.choices[0].message.content or ""
    payload = _clean_json_payload(raw)
    try:
        return SummaryContent.model_validate(json.loads(payload))
    except (json.JSONDecodeError, ValidationError):
        repaired = _clean_json_payload(await _repair_json(client, raw))
        try:
            return SummaryContent.model_validate(json.loads(repaired))
        except (json.JSONDecodeError, ValidationError) as exc:
            raise RuntimeError("Failed to parse summary generation output") from exc
