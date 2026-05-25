from types import SimpleNamespace

from app.ai.rag import MAX_HISTORY_CONTEXT_BYTES, _trim_history_to_budget


def test_chat_history_is_conservatively_bounded_to_four_thousand_tokens():
    messages = [
        SimpleNamespace(role="system", content="Resumo importante."),
        *[SimpleNamespace(role="user", content="x" * 1200) for _ in range(6)],
    ]

    selected = _trim_history_to_budget(messages)

    assert selected[0].role == "system"
    assert sum(len(message.content.encode("utf-8")) for message in selected) <= MAX_HISTORY_CONTEXT_BYTES
    assert selected[-1] is messages[-1]
