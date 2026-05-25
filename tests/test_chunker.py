from app.pipeline.chunker import chunk_pages, chunk_text


def test_short_text_does_not_repeat_suffix_chunks():
    chunks = chunk_text("abc")

    assert [chunk["content"] for chunk in chunks] == ["abc"]


def test_long_text_stops_after_overlapping_final_chunk():
    chunks = chunk_text("A" * 2010)

    assert len(chunks) == 2
    assert len(chunks[0]["content"]) == 2000
    assert len(chunks[1]["content"]) == 210


def test_page_and_note_metadata_are_preserved_without_tail_cascade():
    page_chunks = chunk_pages([{"text": "pagina curta", "page_number": 4, "section": None}])
    note_chunks = chunk_text("nota curta", is_note=True)

    assert len(page_chunks) == 1
    assert page_chunks[0]["metadata"]["page_number"] == 4
    assert len(note_chunks) == 1
    assert note_chunks[0]["metadata"]["is_note"] is True
