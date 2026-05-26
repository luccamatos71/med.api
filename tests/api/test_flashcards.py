from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from app.api.v1.routes.flashcards import _row_to_response


class _SqlAlchemyRowLike:
    def __init__(self, *values):
        self._values = values

    def __iter__(self):
        return iter(self._values)


def test_row_to_response_reads_selected_columns_positionally():
    user_id = uuid4()
    topic_id = uuid4()
    subject_id = uuid4()
    card = SimpleNamespace(
        id=uuid4(),
        user_id=user_id,
        topic_id=topic_id,
        material_id=None,
        doubt_id=None,
        source="ai_generated",
        front="Pergunta",
        back="Resposta",
        source_snippet=None,
        page_number=None,
        ai_approved_at=None,
        archived_at=None,
        created_at=datetime.now(timezone.utc),
    )

    response = _row_to_response(
        _SqlAlchemyRowLike(card, "ICC", "Cardiologia", None, subject_id)
    )

    assert response.topic_name == "ICC"
    assert response.subject_name == "Cardiologia"
    assert response.subject_id == subject_id
