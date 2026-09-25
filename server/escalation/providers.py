"""Cloud LLM providers. Every provider speaks the same normalized shape the rest of the
backend uses (Ollama's): `chat()` returns {"message": {"role", "content", "tool_calls"?},
"done", "usage"} and accepts OpenAI-style `tools` + Ollama-style tool/tool_call messages, so
Anthony's tool loop (tools/caller.py) can run on any of them. `estimate_cost_for(model, ...)`
prices any model a provider serves — the Selector and the spend ledger rely on it.
"""
import json
import logging
from abc import ABC, abstractmethod
from typing import AsyncIterator

import anthropic
import httpx

from config import settings

log = logging.getLogger("dexter.escalation.providers")


class LLMProvider(ABC):
    name: str
    DEFAULT_MODEL: str
    PRICING: dict[str, tuple[float, float]] = {}

    @abstractmethod
    async def chat(
        self, messages: list[dict], model: str, stream: bool = False, tools: list[dict] | None = None,
    ) -> dict | AsyncIterator:
        ...

    @abstractmethod
    async def available(self) -> bool:
        ...

    def estimate_cost_for(self, model: str, input_tokens: int, output_tokens: int) -> float:
        per_m_in, per_m_out = self.PRICING.get(model, self.PRICING.get(self.DEFAULT_MODEL, (0.0, 0.0)))
        return (input_tokens * per_m_in + output_tokens * per_m_out) / 1_000_000

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        return self.estimate_cost_for(self.DEFAULT_MODEL, input_tokens, output_tokens)


# ---------------------------------------------------------------- OpenAI-compatible (DeepSeek, OpenAI, Groq)

class OpenAICompatProvider(LLMProvider):
    """Chat Completions with tool calling, normalized to Ollama's tool_call shape."""

    BASE_URL: str
    TIMEOUT_S = 180

    def _api_key(self) -> str:
        raise NotImplementedError

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._api_key()}", "Content-Type": "application/json"}

    async def available(self) -> bool:
        return bool(self._api_key())

    def _convert_messages_out(self, messages: list[dict]) -> list[dict]:
        out = []
        for m in messages:
            msg = {"role": m.get("role", "user"), "content": m.get("content") or ""}
            tool_calls = m.get("tool_calls")
            if tool_calls:
                msg["tool_calls"] = [
                    {
                        "id": tc.get("id", f"call_{i}"),
                        "type": "function",
                        "function": {
                            "name": tc.get("function", {}).get("name", ""),
                            "arguments": json.dumps(tc.get("function", {}).get("arguments", {}))
                            if isinstance(tc.get("function", {}).get("arguments"), dict)
                            else tc.get("function", {}).get("arguments", "{}"),
                        },
                    }
                    for i, tc in enumerate(tool_calls)
                ]
            if m.get("role") == "tool":
                msg["tool_call_id"] = m.get("tool_call_id", "")
            out.append(msg)
        return out

    @staticmethod
    def _normalize_tool_calls(raw: list[dict] | None) -> list[dict]:
        if not raw:
            return []
        normalized = []
        for tc in raw:
            fn = tc.get("function", {})
            args = fn.get("arguments", "{}")
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            normalized.append({"id": tc.get("id", ""), "function": {"name": fn.get("name", ""), "arguments": args}})
        return normalized

    async def chat(
        self, messages: list[dict], model: str, stream: bool = False, tools: list[dict] | None = None,
    ) -> dict | AsyncIterator:
        body: dict = {"model": model, "messages": self._convert_messages_out(messages)}
        if tools:
            body["tools"] = tools
        if stream:
            body["stream"] = True
            return self._stream_chat(body)

        async with httpx.AsyncClient(timeout=self.TIMEOUT_S) as client:
            resp = await client.post(self.BASE_URL, headers=self._headers(), json=body)
            resp.raise_for_status()
            data = resp.json()
            message = data["choices"][0]["message"]
            result = {
                "message": {
                    "role": "assistant",
                    "content": message.get("content") or "",
                    "tool_calls": self._normalize_tool_calls(message.get("tool_calls")),
                },
                "done": True,
                "usage": data.get("usage", {}),
            }
            if not result["message"]["tool_calls"]:
                del result["message"]["tool_calls"]
            return result

    async def _stream_chat(self, body: dict) -> AsyncIterator:
        headers = self._headers()

        async def _iter():
            async with httpx.AsyncClient(timeout=self.TIMEOUT_S) as client:
                async with client.stream("POST", self.BASE_URL, headers=headers, json=body) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        payload = line[6:].strip()
                        if payload == "[DONE]":
                            break
                        try:
                            event = json.loads(payload)
                        except json.JSONDecodeError:
                            continue
                        choice = event.get("choices", [{}])[0]
                        content = choice.get("delta", {}).get("content") or ""
                        done = choice.get("finish_reason") is not None
                        frame = {"message": {"content": content}, "done": done}
                        if done and event.get("usage"):
                            frame["usage"] = event["usage"]
                        yield frame
        return _iter()


class DeepSeekProvider(OpenAICompatProvider):
    name = "deepseek"
    BASE_URL = "https://api.deepseek.com/v1/chat/completions"
    PRICING = {
        "deepseek-chat": (0.27, 1.10),
        "deepseek-reasoner": (0.55, 2.19),
    }
    DEFAULT_MODEL = "deepseek-chat"

    def _api_key(self) -> str:
        return settings.deepseek_api_key


class OpenAIProvider(OpenAICompatProvider):
    name = "openai"
    BASE_URL = "https://api.openai.com/v1/chat/completions"
    TIMEOUT_S = 120
    # Prices for the configured model come from DEXTER_OPENAI_PRICE_IN/OUT when set.
    PRICING = {
        "gpt-4o": (2.50, 10.0),
        "gpt-4o-mini": (0.15, 0.60),
    }

    @property
    def DEFAULT_MODEL(self) -> str:  # type: ignore[override]
        return settings.openai_model

    def _api_key(self) -> str:
        return settings.openai_api_key

    def estimate_cost_for(self, model: str, input_tokens: int, output_tokens: int) -> float:
        if model == settings.openai_model and settings.openai_price_in is not None and settings.openai_price_out is not None:
            return (input_tokens * settings.openai_price_in + output_tokens * settings.openai_price_out) / 1_000_000
        return super().estimate_cost_for(model, input_tokens, output_tokens)


class GroqProvider(OpenAICompatProvider):
    name = "groq"
    BASE_URL = "https://api.groq.com/openai/v1/chat/completions"
    TIMEOUT_S = 60
    DEFAULT_MODEL = "llama-3.3-70b-versatile"
    PRICING = {"llama-3.3-70b-versatile": (0.59, 0.79)}

    def _api_key(self) -> str:
        return settings.groq_api_key


# ---------------------------------------------------------------- Anthropic (official SDK)

# Models that get the server-side refusal fallback by default (Claude API guidance: a declined
# request is re-run on Anthropic's recommended substitute instead of returning a refusal).
_FALLBACK_MODELS = {"claude-opus-5", "claude-fable-5-1"}
_FALLBACK_BETA = "server-side-fallback-2026-07-01"


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    PRICING = {
        "claude-fable-5-1": (10.0, 50.0),
        "claude-opus-5-5": (4.0, 20.0),
        "claude-opus-5": (5.0, 25.0),
        "claude-sonnet-5": (2.0, 10.0),
        "claude-haiku-4-5": (1.0, 5.0),
    }
    MAX_TOKENS = 16000

    @property
    def DEFAULT_MODEL(self) -> str:  # type: ignore[override]
        return settings.anthropic_model

    def __init__(self) -> None:
        self._client: anthropic.AsyncAnthropic | None = None

    def _sdk(self) -> anthropic.AsyncAnthropic:
        if self._client is None:
            self._client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        return self._client

    async def available(self) -> bool:
        return bool(settings.anthropic_api_key)

    @staticmethod
    def _convert_tools(tools: list[dict] | None) -> list[dict]:
        out = []
        for t in tools or []:
            fn = t.get("function", t)
            out.append({
                "name": fn["name"],
                "description": fn.get("description", ""),
                "input_schema": fn.get("parameters") or {"type": "object", "properties": {}},
            })
        return out

    @staticmethod
    def convert_messages(messages: list[dict]) -> tuple[str | None, list[dict]]:
        """Ollama-shaped history → (system, Messages API messages). Assistant turns produced by
        this provider carry their original content blocks in `_anthropic_content` (thinking +
        tool_use), which are sent back unchanged; consecutive tool results become one user
        message of tool_result blocks."""
        system_parts: list[str] = []
        out: list[dict] = []
        for m in messages:
            role = m.get("role")
            if role == "system":
                system_parts.append(m.get("content") or "")
                continue
            if role == "tool":
                block = {"type": "tool_result", "tool_use_id": m.get("tool_call_id", ""), "content": str(m.get("content") or "")}
                if out and out[-1]["role"] == "user" and isinstance(out[-1]["content"], list) \
                        and all(b.get("type") == "tool_result" for b in out[-1]["content"]):
                    out[-1]["content"].append(block)
                else:
                    out.append({"role": "user", "content": [block]})
                continue
            if role == "assistant" and m.get("_anthropic_content"):
                out.append({"role": "assistant", "content": m["_anthropic_content"]})
                continue
            if role == "assistant" and m.get("tool_calls"):
                blocks: list[dict] = [{"type": "text", "text": m["content"]}] if m.get("content") else []
                for i, tc in enumerate(m["tool_calls"]):
                    fn = tc.get("function", {})
                    args = fn.get("arguments", {})
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except json.JSONDecodeError:
                            args = {}
                    blocks.append({"type": "tool_use", "id": tc.get("id") or f"call_{i}", "name": fn.get("name", ""), "input": args})
                out.append({"role": "assistant", "content": blocks})
                continue
            content = m.get("content") or ""
            if out and out[-1]["role"] == role and isinstance(out[-1]["content"], str):
                out[-1]["content"] += "\n" + content
            else:
                out.append({"role": role or "user", "content": content})
        if out and out[0]["role"] != "user":
            out.insert(0, {"role": "user", "content": "."})
        return ("\n\n".join(p for p in system_parts if p) or None), out

    def _request(self, messages: list[dict], model: str, tools: list[dict] | None) -> dict:
        system, converted = self.convert_messages(messages)
        req: dict = {"model": model, "max_tokens": self.MAX_TOKENS, "messages": converted}
        if system:
            req["system"] = system
        if tools:
            req["tools"] = self._convert_tools(tools)
        return req

    async def chat(
        self, messages: list[dict], model: str, stream: bool = False, tools: list[dict] | None = None,
    ) -> dict | AsyncIterator:
        req = self._request(messages, model, tools)
        if stream:
            return self._stream_chat(req)
        client = self._sdk()
        if model in _FALLBACK_MODELS:
            response = await client.beta.messages.create(**req, betas=[_FALLBACK_BETA], fallbacks="default")
        else:
            response = await client.messages.create(**req)
        return self.normalize_response(response)

    @staticmethod
    def normalize_response(response) -> dict:
        usage = {"input_tokens": response.usage.input_tokens, "output_tokens": response.usage.output_tokens}
        if response.stop_reason == "refusal":
            category = getattr(getattr(response, "stop_details", None), "category", None)
            return {
                "message": {"role": "assistant", "content": f"[Claude declined this request{f' ({category})' if category else ''}]"},
                "done": True, "usage": usage,
            }
        text = "".join(b.text for b in response.content if b.type == "text")
        tool_calls = [
            {"id": b.id, "function": {"name": b.name, "arguments": b.input}}
            for b in response.content if b.type == "tool_use"
        ]
        message: dict = {"role": "assistant", "content": text}
        if tool_calls:
            message["tool_calls"] = tool_calls
            # keep thinking + tool_use blocks verbatim for the next request in this loop
            message["_anthropic_content"] = [b.model_dump(exclude_none=True) for b in response.content]
        return {"message": message, "done": True, "usage": usage}

    async def _stream_chat(self, req: dict) -> AsyncIterator:
        client = self._sdk()
        model = req["model"]

        async def _iter():
            if model in _FALLBACK_MODELS:
                manager = client.beta.messages.stream(**req, betas=[_FALLBACK_BETA], fallbacks="default")
            else:
                manager = client.messages.stream(**req)
            async with manager as s:
                async for text in s.text_stream:
                    yield {"message": {"content": text}, "done": False}
                final = await s.get_final_message()
            yield {
                "message": {"content": ""}, "done": True,
                "usage": {"input_tokens": final.usage.input_tokens, "output_tokens": final.usage.output_tokens},
            }
        return _iter()
