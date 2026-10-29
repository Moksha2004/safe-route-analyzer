from __future__ import annotations

import json
from typing import Any

import httpx


class NebiusClient:
    def __init__(self, api_key: str, base_url: str, client: httpx.AsyncClient | None = None) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.client = client or httpx.AsyncClient(timeout=30.0)
        self._owns_client = client is None

    async def close(self) -> None:
        if self._owns_client:
            await self.client.aclose()

    async def chat_json(self, model: str, system: str, user: str, timeout: float = 30.0, max_tokens: int = 800) -> dict[str, Any]:
        response = await self.client.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": model,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                "response_format": {"type": "json_object"},
                "temperature": 0.2,
                "max_tokens": max_tokens,
                # Nemotron 3 reasons by default and can spend the whole budget thinking, returning content=null.
                "chat_template_kwargs": {"enable_thinking": False},
            },
            timeout=timeout,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"].get("content")
        if not content:
            raise ValueError("Model returned no content")
        value = json.loads(content)
        return value if isinstance(value, dict) else {}
