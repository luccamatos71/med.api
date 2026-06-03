"""Deterministic study-plan builder with an optional AI strategy overview.

Distributes topic study, spaced reviews and periodic mock exams across the days
up to the exam date. The math is deterministic (reliable); the AI only writes a
short motivational/strategy overview (best-effort).
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

from openai import AsyncOpenAI

from app.core.config import settings

logger = logging.getLogger(__name__)
MODEL = "gpt-4o-mini"


def build_plan(
    *,
    today: date,
    exam_date: date,
    topics: list[dict[str, Any]],  # [{id, name, subject_id, subject_name}]
    due_by_date: dict[str, int] | None = None,  # ISO date -> count of FSRS cards due
) -> dict[str, Any]:
    due_by_date = due_by_date or {}
    total_days = (exam_date - today).days
    if total_days < 1:
        total_days = 1

    days: list[dict[str, Any]] = []
    n_topics = len(topics)

    # Spread topics across the first ~70% of the period (leave the tail for revision).
    study_window = max(1, int(total_days * 0.7))
    topic_day = {}
    for i, t in enumerate(topics):
        d = int(i * study_window / n_topics) if n_topics else 0
        topic_day.setdefault(d, []).append(t)

    for offset in range(total_days + 1):
        current = today + timedelta(days=offset)
        tasks: list[dict[str, Any]] = []

        # New topics scheduled for this day
        for t in topic_day.get(offset, []):
            tasks.append({
                "type": "study",
                "label": f"Estudar: {t['name']}",
                "topic_id": str(t["id"]),
                "subject_id": str(t["subject_id"]) if t.get("subject_id") else None,
            })

        # Real FSRS reviews due this day take priority; otherwise a spaced
        # review every 2 days (and daily in the final week).
        due_count = due_by_date.get(current.isoformat(), 0)
        in_final_week = (total_days - offset) <= 7
        if due_count > 0:
            tasks.append({"type": "review", "label": f"Revisar {due_count} flashcard(s) agendado(s)", "topic_id": None, "subject_id": None})
        elif offset > 0 and (offset % 2 == 0 or in_final_week):
            tasks.append({"type": "review", "label": "Revisar flashcards do dia", "topic_id": None, "subject_id": None})

        # Weekly mock exam, plus one the day before the exam
        if (offset > 0 and offset % 7 == 0) or offset == total_days - 1:
            tasks.append({"type": "exam", "label": "Simulado", "topic_id": None, "subject_id": None})

        if offset == total_days:
            tasks = [{"type": "exam", "label": "🎯 Dia da prova — revisão leve", "topic_id": None, "subject_id": None}]

        if tasks:
            days.append({"date": current.isoformat(), "tasks": tasks})

    summary = {
        "total_days": total_days,
        "topics": n_topics,
        "study_sessions": sum(1 for d in days for t in d["tasks"] if t["type"] == "study"),
        "reviews": sum(1 for d in days for t in d["tasks"] if t["type"] == "review"),
        "exams": sum(1 for d in days for t in d["tasks"] if t["type"] == "exam"),
    }
    return {"days": days, "summary": summary}


async def generate_overview(
    *, exam_date: date, total_days: int, subjects: list[str], topic_count: int
) -> str:
    fallback = (
        f"Plano até {exam_date.strftime('%d/%m')}: {total_days} dias para cobrir {topic_count} tópicos "
        f"de {', '.join(subjects) if subjects else 'suas matérias'}. Estude os tópicos novos primeiro, "
        "revise em intervalos crescentes e faça simulados semanais para medir o progresso."
    )
    if not settings.OPENAI_API_KEY:
        return fallback
    try:
        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        resp = await client.chat.completions.create(
            model=MODEL,
            temperature=0.5,
            messages=[
                {"role": "system", "content": "Você é uma mentora de estudos de medicina, direta e motivadora."},
                {
                    "role": "user",
                    "content": (
                        f"Escreva 2-3 frases de estratégia para um cronograma de estudos de {total_days} dias "
                        f"até a prova em {exam_date.strftime('%d/%m/%Y')}, cobrindo {topic_count} tópicos de "
                        f"{', '.join(subjects) if subjects else 'medicina'}. Tom encorajador, prático, em português."
                    ),
                },
            ],
        )
        text = (resp.choices[0].message.content or "").strip()
        return text or fallback
    except Exception:
        logger.debug("Overview generation failed; using fallback", exc_info=True)
        return fallback
