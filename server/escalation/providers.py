import json
import logging
from abc import ABC, abstractmethod
from typing import AsyncIterator

import httpx

from config import settings

log = logging.getLogger("dexter.escalation.providers")


class LLMProvider(ABC):
    name: str

    @abstractmethod
    async def chat(self, messages: list[dict], model: str, stream: bool = False) -> dict | AsyncIterator:
        ...

    @abstractmethod
    async def available(self) -> bool:
        ...

    @abstractmethod
    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        ...


def _parse_sse_stream(response: httpx.Response):
    async def _iter():
        async for line in response.aiter_lines():
            if not line.startswith("data: "):
                continue
            payload = line[6:].strip()
            if payload == "[DONE]":
                break
            try:
                yield json.loads(payload)
            except json.JSONDecodeError:
                continue
    return _iter()


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    PRICING = {
        "claude-sonnet-4-20250514": (3.0, 15.0),
        "claude-opus-4-20250514": (15.0, 75.0),
    }
    DEFAULT_MODEL = "claude-sonnet-4-20250514"

    def _convert_messages(self, messages: list[dict]) -> tuple[str | None, list[dict]]:
        system = None
        converted = []
        for m in messages:
            if m.get("role") == "system":
                system = m.get("content", "")
                continue
            converted.append({"role": m["role"], "content": m.get("content", "")})
        if converted and converted[0]["role"] != "user":
            converted.insert(0, {"role": "user", "content": "."})
        prev_role = None
        deduped = []
        for msg in converted:
            if msg["role"] == prev_role:
                deduped[-1]["content"] += "\n" + msg["content"]
            else:
                deduped.append(msg)
            prev_role = msg["role"]
        return system, deduped

    async def chat(self, messages: list[dict], model: str, stream: bool = False) -> dict | AsyncIterator:
        system, converted = self._convert_messages(messages)
        body: dict = {
            "model": model,
            "messages": converted,
            "max_tokens": 4096,
        }
        if system:
            body["system"] = system
        if stream:
            body["stream"] = True

        headers = {
            "x-api-key": settings.anthropic_api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        if stream:
            return self._stream_chat(headers, body)

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post("https://api.anthropic.com/v1/messages", headers=headers, json=body)
            resp.raise_for_status()
            data = resp.json()
            content = ""
            for block in data.get("content", []):
                if block.get("type") == "text":
                    content += block["text"]
            return {
                "message": {"role": "assistant", "content": content},
                "done": True,
                "usage": data.get("usage", {}),
            }

    async def _stream_chat(self, headers: dict, body: dict) -> AsyncIterator:
        async def _iter():
            async with httpx.AsyncClient(timeout=120) as client:
                async with client.stream("POST", "https://api.anthropic.com/v1/messages", headers=headers, json=body) as resp:
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
                        if event.get("type") == "content_block_delta":
                            delta = event.get("delta", {})
                            if delta.get("type") == "text_delta":
                                yield {"message": {"content": delta["text"]}, "done": False}
                        elif event.get("type") == "message_delta":
                            usage = event.get("usage", {})
                            yield {"message": {"content": ""}, "done": True, "usage": usage}
        return _iter()

    async def available(self) -> bool:
        return bool(settings.anthropic_api_key)

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        per_m_in, per_m_out = self.PRICING.get(self.DEFAULT_MODEL, (3.0, 15.0))
        return (input_tokens * per_m_in + output_tokens * per_m_out) / 1_000_000


class OpenAIProvider(LLMProvider):
    name = "openai"

    PRICING = {
        "gpt-4o": (2.50, 10.0),
        "gpt-4o-mini": (0.15, 0.60),
    }
    DEFAULT_MODEL = "gpt-4o"

    async def chat(self, messages: list[dict], model: str, stream: bool = False) -> dict | AsyncIterator:
        body: dict = {
            "model": model,
            "messages": [{"role": m["role"], "content": m.get("content", "")} for m in messages],
        }
        if stream:
            body["stream"] = True

        headers = {
            "Authorization": f"Bearer {settings.openai_api_key}",
            "Content-Type": "application/json",
        }

        if stream:
            return self._stream_chat(headers, body)

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post("https://api.openai.com/v1/chat/completions", headers=headers, json=body)
            resp.raise_for_status()
            data = resp.json()
            choice = data["choices"][0]
            return {
                "message": {"role": "assistant", "content": choice["message"]["content"]},
                "done": True,
                "usage": data.get("usage", {}),
            }

    async def _stream_chat(self, headers: dict, body: dict) -> AsyncIterator:
        async def _iter():
            async with httpx.AsyncClient(timeout=120) as client:
                async with client.stream("POST", "https://api.openai.com/v1/chat/completions", headers=headers, json=body) as resp:
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
                        delta = event.get("choices", [{}])[0].get("delta", {})
                        content = delta.get("content", "")
                        done = event.get("choices", [{}])[0].get("finish_reason") is not None
                        yield {"message": {"content": content}, "done": done}
        return _iter()

    async def available(self) -> bool:
        return bool(settings.openai_api_key)

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        per_m_in, per_m_out = self.PRICING.get(self.DEFAULT_MODEL, (2.50, 10.0))
        return (input_tokens * per_m_in + output_tokens * per_m_out) / 1_000_000


class GroqProvider(LLMProvider):
    name = "groq"

    DEFAULT_MODEL = "llama-3.3-70b-versatile"

    async def chat(self, messages: list[dict], model: str, stream: bool = False) -> dict | AsyncIterator:
        body: dict = {
            "model": model,
            "messages": [{"role": m["role"], "content": m.get("content", "")} for m in messages],
        }
        if stream:
            body["stream"] = True

        headers = {
            "Authorization": f"Bearer {settings.groq_api_key}",
            "Content-Type": "application/json",
        }

        if stream:
            return self._stream_chat(headers, body)

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=body)
            resp.raise_for_status()
            data = resp.json()
            choice = data["choices"][0]
            return {
                "message": {"role": "assistant", "content": choice["message"]["content"]},
                "done": True,
                "usage": data.get("usage", {}),
            }

    async def _stream_chat(self, headers: dict, body: dict) -> AsyncIterator:
        async def _iter():
            async with httpx.AsyncClient(timeout=60) as client:
                async with client.stream("POST", "https://api.groq.com/openai/v1/chat/completions", headers=headers, json=body) as resp:
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
                        delta = event.get("choices", [{}])[0].get("delta", {})
                        content = delta.get("content", "")
                        done = event.get("choices", [{}])[0].get("finish_reason") is not None
                        yield {"message": {"content": content}, "done": done}
        return _iter()

    async def available(self) -> bool:
        return bool(settings.groq_api_key)

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        return 0.0
