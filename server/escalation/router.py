import logging

from config import settings
from models import EscalationLevel, ModelRoute
from escalation.classifier import TaskClassifier
from escalation.providers import LLMProvider
from escalation.tracker import SpendTracker

log = logging.getLogger("dexter.escalation.router")


class ModelRouter:
    def __init__(
        self,
        classifier: TaskClassifier,
        providers: dict[str, LLMProvider],
        ollama_client,
        tracker: SpendTracker,
    ):
        self.classifier = classifier
        self.providers = providers
        self.ollama = ollama_client
        self.tracker = tracker

    async def route(
        self,
        message: str,
        context: list[dict] | None = None,
        force_level: EscalationLevel | None = None,
    ) -> ModelRoute:
        level = force_level if force_level is not None else self.classifier.classify(message, context)

        if level == EscalationLevel.FAST:
            groq = self.providers.get("groq")
            if groq and await groq.available():
                return ModelRoute(
                    level=EscalationLevel.FAST,
                    provider="groq",
                    model="llama-3.3-70b-versatile",
                    reason="simple query → groq fast",
                )
            return ModelRoute(
                level=EscalationLevel.FAST,
                provider="ollama",
                model=settings.ollama_fast_model,
                reason="simple query → fast model",
            )

        if level == EscalationLevel.CLOUD:
            if self.tracker.budget_remaining() <= 0:
                log.warning("Daily cloud budget exhausted — falling back to local")
                return ModelRoute(
                    level=EscalationLevel.LOCAL,
                    provider="ollama",
                    model=settings.ollama_model,
                    reason="daily cloud budget exhausted — falling back to local",
                )

            for provider_name in ("anthropic", "openai"):
                provider = self.providers.get(provider_name)
                if provider and await provider.available():
                    default_model = getattr(provider, "DEFAULT_MODEL", provider_name)
                    return ModelRoute(
                        level=EscalationLevel.CLOUD,
                        provider=provider_name,
                        model=default_model,
                        reason=f"complex task → {provider_name}",
                    )

            log.warning("No cloud API configured — falling back to local")
            return ModelRoute(
                level=EscalationLevel.LOCAL,
                provider="ollama",
                model=settings.ollama_model,
                reason="no cloud API configured — falling back to local",
            )

        return ModelRoute(
            level=EscalationLevel.LOCAL,
            provider="ollama",
            model=settings.ollama_model,
            reason="default local",
        )

    async def chat(self, messages: list[dict], route: ModelRoute, stream: bool = False):
        if route.provider == "ollama":
            return await self.ollama.chat(messages, model=route.model, stream=stream)

        provider = self.providers.get(route.provider)
        if not provider:
            log.error("Provider %s not found, falling back to ollama", route.provider)
            return await self.ollama.chat(messages, model=settings.ollama_model, stream=stream)

        result = await provider.chat(messages, model=route.model, stream=stream)

        if isinstance(result, dict) and not stream:
            usage = result.get("usage", {})
            input_tokens = usage.get("input_tokens", usage.get("prompt_tokens", 0))
            output_tokens = usage.get("output_tokens", usage.get("completion_tokens", 0))
            cost = provider.estimate_cost(input_tokens, output_tokens)
            self.tracker.record(
                provider=route.provider,
                model=route.model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost,
            )

        return result
