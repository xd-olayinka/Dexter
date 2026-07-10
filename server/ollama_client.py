import logging
from ollama import AsyncClient

log = logging.getLogger("dexter.ollama")


class OllamaClient:
    def __init__(self, base_url: str, model: str, fast_model: str, embed_model: str):
        self.model = model
        self.fast_model = fast_model
        self.embed_model = embed_model
        self.client = AsyncClient(host=base_url)

    async def chat(
        self,
        messages: list[dict],
        model: str | None = None,
        stream: bool = False,
    ):
        target = model or self.model
        try:
            response = await self.client.chat(
                model=target,
                messages=messages,
                stream=stream,
            )
            return response
        except Exception as e:
            log.error("Ollama chat error: %s", e)
            if stream:
                async def _error_stream():
                    yield {"message": {"content": f"[Ollama unavailable: {e}]"}, "done": True}
                return _error_stream()
            return {
                "message": {"role": "assistant", "content": f"[Ollama unavailable: {e}]"},
                "done": True,
            }

    async def embed(self, text: str) -> list[float]:
        try:
            result = await self.client.embed(model=self.embed_model, input=text)
            return result["embeddings"][0]
        except Exception as e:
            log.error("Ollama embed error: %s", e)
            return []

    async def list_models(self) -> list[str]:
        try:
            result = await self.client.list()
            return [m.model for m in result.models]
        except Exception as e:
            log.error("Ollama list_models error: %s", e)
            return []

    async def health(self) -> bool:
        try:
            await self.client.list()
            return True
        except Exception:
            return False
