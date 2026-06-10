from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any, Callable, Protocol
from urllib import request


class LLMClient(Protocol):
    def generate(self, prompts: list[str], *, system_prompt: str = "") -> list[str]:
        """Generate one response per prompt."""


class StaticLLMClient:
    """Deterministic LLM client for tests and dry-runs."""

    def __init__(self, responses: Iterable[str]):
        self._responses = list(responses)
        self.prompts: list[str] = []

    def generate(self, prompts: list[str], *, system_prompt: str = "") -> list[str]:
        self.prompts.extend(prompts)
        if len(prompts) > len(self._responses):
            raise ValueError("StaticLLMClient does not have enough responses")
        out = self._responses[: len(prompts)]
        del self._responses[: len(prompts)]
        return out


Transport = Callable[[str, dict[str, Any], int], dict[str, Any]]


class OpenAICompatibleLLMClient:
    """OpenAI-compatible chat completions client, suitable for local LM Studio."""

    def __init__(
        self,
        *,
        base_url: str = "http://127.0.0.1:1234/v1",
        model: str = "gemma-4-31b-it",
        timeout_sec: int = 120,
        temperature: float = 0.2,
        transport: Transport | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_sec = timeout_sec
        self.temperature = temperature
        self._transport = transport or _post_json

    def generate(self, prompts: list[str], *, system_prompt: str = "") -> list[str]:
        return [self._generate_one(prompt, system_prompt=system_prompt) for prompt in prompts]

    def _generate_one(self, prompt: str, *, system_prompt: str) -> str:
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "stream": False,
        }
        data = self._transport(
            f"{self.base_url}/chat/completions",
            payload,
            self.timeout_sec,
        )
        try:
            return str(data["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError(f"Invalid OpenAI-compatible response: {data!r}") from exc


def _post_json(url: str, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        raw = resp.read().decode("utf-8")
    return json.loads(raw)
