from __future__ import annotations

import asyncio
import json
import urllib.request
from dataclasses import dataclass
from typing import Any

from mythweaver.schemas.contracts import RequirementProfile


@dataclass(frozen=True)
class OpenAICompatibleConfig:
    base_url: str
    model: str
    api_key: str | None = None


class OpenAICompatibleAdapter:
    """Optional profile adapter for Ollama, LM Studio, llama.cpp, or hosted compatible APIs."""

    def __init__(self, config: OpenAICompatibleConfig) -> None:
        self.config = config

    async def profile_from_prompt(self, prompt: str) -> RequirementProfile:
        raw = await asyncio.to_thread(self._request_profile, prompt)
        return RequirementProfile.model_validate(raw)

    def _request_profile(self, prompt: str) -> dict[str, Any]:
        system = (
            "Return only JSON matching MythWeaver RequirementProfile fields. "
            "Do not invent mod IDs. Do not include markdown."
        )
        body = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        }
        url = self.config.base_url.rstrip("/") + "/chat/completions"
        headers = {"Content-Type": "application/json", "User-Agent": "MythWeaver/0.1.0"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        request = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = json.loads(response.read().decode("utf-8"))
        content = payload["choices"][0]["message"]["content"]
        return json.loads(content)

