"""Embedding function factory for SemanticMemory.

Kept separate from ollama_client so SemanticMemory never has to know whether an
embedding provider exists at all. `OllamaClient.embed` already catches its own
errors and returns `[]` on failure (Ollama down, model not pulled, etc.) — and
SemanticMemory already treats an empty vector as "nothing to index/recall" — so
this is a thin wrapper, not a second health check, to avoid doubling network calls.
"""


def make_embed_fn(ollama_client):
    async def embed(text: str) -> list[float]:
        if not text.strip():
            return []
        return await ollama_client.embed(text)

    return embed
