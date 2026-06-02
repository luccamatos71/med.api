import json
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from app.services import exam_generator
from app.services.study_plan_generator import build_plan

EXAM_JSON = {
    "questions": [
        {"stem": "Q1?", "options": ["a", "b", "c", "d"], "correct_index": 1, "explanation": "pq b", "source_page": 3},
        {"stem": "Q2?", "options": ["w", "x", "y", "z"], "correct_index": 0, "explanation": "pq w", "source_page": None},
    ]
}


def _client(payload, capture):
    class _Comp:
        async def create(self, **kw):
            capture["messages"] = kw["messages"]
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=payload))])

    class _Client:
        def __init__(self):
            self.chat = SimpleNamespace(completions=_Comp())

    return _Client()


@pytest.mark.asyncio
async def test_exam_generator_parses_and_preserves_correct_answer(monkeypatch):
    capture = {}
    monkeypatch.setattr(exam_generator.settings, "OPENAI_API_KEY", "k")
    monkeypatch.setattr(exam_generator, "AsyncOpenAI", lambda **_k: _client(json.dumps(EXAM_JSON), capture))

    chunks = [{"content": "conteudo", "metadata": {"page_number": 3}}]
    questions = await exam_generator.generate_exam_from_chunks(chunks, 2)

    assert len(questions) == 2
    for q in questions:
        # after shuffle, the correct_index must still point to the right option text
        assert 0 <= q["correct_index"] < len(q["options"])
    # Q1 correct text was "b"
    assert questions[0]["options"][questions[0]["correct_index"]] == "b"


def test_build_plan_distributes_and_summarises():
    today = date(2026, 6, 2)
    exam = today + timedelta(days=20)
    topics = [
        {"id": f"t{i}", "name": f"Tópico {i}", "subject_id": "s1", "subject_name": "Cardio"}
        for i in range(5)
    ]
    plan = build_plan(today=today, exam_date=exam, topics=topics)

    assert plan["summary"]["topics"] == 5
    assert plan["summary"]["study_sessions"] == 5  # all topics scheduled
    assert plan["summary"]["exams"] >= 1
    assert len(plan["days"]) > 0
    # last day is the exam day
    assert plan["days"][-1]["date"] == exam.isoformat()
