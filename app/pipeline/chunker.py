"""Text chunker for material processing pipeline.

Target: ~500 tokens per chunk using 4 chars/token estimate (~2000 chars).
Overlap: ~50 tokens (~200 chars).
Break preference: double newline > single newline > period+space > space.
"""

TARGET_CHARS = 2000
OVERLAP_CHARS = 200


def _find_break(text: str, start: int, end: int) -> int:
    """Find the best break point in text[start:end] using break preferences.

    Preference order: double newline > single newline > period+space > space.
    Falls back to hard cut at end if no break point found.
    """
    segment = text[start:end]

    # Try double newline (paragraph break)
    pos = segment.rfind("\n\n")
    if pos != -1:
        return start + pos + 2

    # Try single newline
    pos = segment.rfind("\n")
    if pos != -1:
        return start + pos + 1

    # Try period followed by space
    pos = segment.rfind(". ")
    if pos != -1:
        return start + pos + 2

    # Try space
    pos = segment.rfind(" ")
    if pos != -1:
        return start + pos + 1

    # Hard cut
    return end


def _chunk_text(
    text: str,
    page_number: int | None = None,
    section: str | None = None,
    is_note: bool = False,
    chunk_index_start: int = 0,
) -> list[dict]:
    """Split a single text string into overlapping chunks."""
    chunks: list[dict] = []
    text_len = len(text)
    start = 0
    idx = chunk_index_start

    while start < text_len:
        end = min(start + TARGET_CHARS, text_len)

        if end < text_len:
            break_point = _find_break(text, start, end)
        else:
            break_point = text_len

        chunk_text = text[start:break_point].strip()
        if chunk_text:
            chunks.append(
                {
                    "content": chunk_text,
                    "metadata": {
                        "page_number": page_number,
                        "section": section,
                        "is_note": is_note,
                        "chunk_index": idx,
                    },
                }
            )
            idx += 1

        # Advance with overlap
        start = max(break_point - OVERLAP_CHARS, start + 1)

    return chunks


def chunk_pages(pages: list[dict]) -> list[dict]:
    """Chunk a list of page dicts from pdf_parser.

    Args:
        pages: List of {"text": str, "page_number": int, "section": str | None}.

    Returns:
        List of chunk dicts with content and metadata.
    """
    all_chunks: list[dict] = []
    for page in pages:
        page_chunks = _chunk_text(
            text=page["text"],
            page_number=page.get("page_number"),
            section=page.get("section"),
            is_note=False,
            chunk_index_start=len(all_chunks),
        )
        all_chunks.extend(page_chunks)
    return all_chunks


def chunk_text(text: str, is_note: bool = False) -> list[dict]:
    """Chunk a plain text or note string.

    Args:
        text: Plain text content.
        is_note: Whether this is a note type material.

    Returns:
        List of chunk dicts with content and metadata.
    """
    return _chunk_text(
        text=text,
        page_number=None,
        section=None,
        is_note=is_note,
        chunk_index_start=0,
    )
