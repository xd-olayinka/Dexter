import logging
import time

from config import settings
from ollama_client import OllamaClient
from escalation.providers import DeepSeekProvider
from escalation.tracker import SpendTracker

log = logging.getLogger("dexter.brain")

HEALTH_TTL_S = 30

STUB_MESSAGE = (
    "[No intelligence provider available — install Ollama (ollama.com) "
    "or set DEXTER_DEEPSEEK_API_KEY in server/.env]"
)


class Brain:
    """Unified intelligence layer. Resolves the active provider per call:
    primary_provider=ollama|deepseek forces one; auto prefers a healthy
    Ollama, falls back to DeepSeek when a key is set, else stubs."""

    def __init__(
        self,
        ollama: OllamaClient,
        deepseek: DeepSeekProvider,
        tracker: SpendTracker | None = None,
    ):
        self.ollama = ollama
        self.deepseek = deepseek
        self.tracker = tracker
        self._ollama_healthy = False
        self._health_checked_at = 0.0

    async def _ollama_ok(self) -> bool:
        now = time.monotonic()
        if now - self._health_checked_at > HEALTH_TTL_S:
            self._ollama_healthy = await self.ollama.health()
            self._health_checked_at = now
        return self._ollama_healthy

    async def resolve(self) -> str:
        mode = settings.primary_provider
        if mode == "ollama":
            return "ollama"
        if mode == "deepseek":
            return "deepseek" if await self.deepseek.available() else "stub"
        if await self._ollama_ok():
            return "ollama"
        if await self.deepseek.available():
            return "deepseek"
        return "stub"

    async def describe(self) -> dict:
        provider = await self.resolve()
        if provider == "ollama":
            model = settings.ollama_model
        elif provider == "deepseek":
            model = settings.deepseek_model
        else:
            model = "—"
        return {"provider": provider, "model": model, "ready": provider != "stub"}

    async def _record_usage(
        self, model: str, usage: dict, task_id: str | None = None,
        business_id: str | None = None, source: str = "chat",
    ) -> float:
        import ledger

        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)
        cost = self.deepseek.estimate_cost_for(model, input_tokens, output_tokens)
        await ledger.record(business_id, "deepseek", model, input_tokens, output_tokens, cost, task_id=task_id, source=source)
        if self.tracker and cost > 0:
            self.tracker.record(
                provider="deepseek",
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost,
                task_id=task_id,
            )
        return cost

    async def chat(
        self,
        messages: list[dict],
        model: str | None = None,
        stream: bool = False,
        tools: list[dict] | None = None,
        reasoning: bool = False,
        task_id: str | None = None,
        business_id: str | None = None,
        source: str = "chat",
    ):
        provider = await self.resolve()

        if provider == "ollama":
            return await self.ollama.chat(messages, model=model, stream=stream, tools=tools)

        if provider == "deepseek":
            target = model or (
                settings.deepseek_reasoner_model if reasoning else settings.deepseek_model
            )
            try:
                if stream:
                    inner = await self.deepseek.chat(messages, model=target, stream=True, tools=tools)

                    async def _tracked():
                        async for frame in inner:
                            if frame.get("done") and frame.get("usage"):
                                await self._record_usage(target, frame["usage"], task_id, business_id, source)
                            yield frame
                    return _tracked()

                response = await self.deepseek.chat(messages, model=target, tools=tools)
                if response.get("usage"):
                    cost = await self._record_usage(target, response["usage"], task_id, business_id, source)
                    response["cost_usd"] = cost
                return response
            except Exception as e:
                log.error("DeepSeek chat error: %s", e)
                if stream:
                    async def _error_stream():
                        yield {"message": {"content": f"[DeepSeek error: {e}]"}, "done": True}
                    return _error_stream()
                return {"message": {"role": "assistant", "content": f"[DeepSeek error: {e}]"}, "done": True}

        if stream:
            async def _stub_stream():
                yield {"message": {"content": STUB_MESSAGE}, "done": True}
            return _stub_stream()
        return {"message": {"role": "assistant", "content": STUB_MESSAGE}, "done": True}
