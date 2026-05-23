"""Embedder module using OpenAI text-embedding-3-small."""
from openai import AsyncOpenAI

from app.core.config import settings

EMBEDDING_MODEL = "text-embedding-3-small"
BATCH_SIZE = 100


async def embed_chunks(chunks: list[dict]) -> list[list[float]]:
    """Generate embeddings for a list of chunk dicts.

    Args:
        chunks: List of chunk dicts with at least a "content" key.

    Returns:
        List of embedding vectors (list of float) in the same order as input.

    Raises:
        RuntimeError: If the OpenAI API call fails.
    """
    if not chunks:
        return []

    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    texts = [chunk["content"] for chunk in chunks]
    all_embeddings: list[list[float]] = []

    for batch_start in range(0, len(texts), BATCH_SIZE):
        batch = texts[batch_start : batch_start + BATCH_SIZE]
        try:
            response = await client.embeddings.create(
                model=EMBEDDING_MODEL,
                input=batch,
            )
        except Exception as exc:
            raise RuntimeError(
                f"Falha ao gerar embeddings (batch {batch_start // BATCH_SIZE + 1}): {exc}"
            ) from exc

        # OpenAI returns embeddings sorted by index
        batch_embeddings = [item.embedding for item in sorted(response.data, key=lambda x: x.index)]
        all_embeddings.extend(batch_embeddings)

    return all_embeddings
