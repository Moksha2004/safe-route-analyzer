from __future__ import annotations

from typing import Any

import httpx


class NebiusClient:
    def __init__(self, api_key: str, base_url: str, client: httpx.AsyncClient | None = None) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.client = client or httpx.AsyncClient(timeout=4.0)
        self._owns_client = client is None

    async def close(self) -> None:
        if self._owns_client:
            await self.client.aclose()

    async def chat_json(self, model: str, system: str, user: str) -> dict[str, Any]:
        response = await self.client.post(f"{self.base_url}/chat/completions", headers={"Authorization": f"Bearer {self.api_key}"}, json={"model": model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}], "response_format": {"type": "json_object"}, "temperature": 0.2})
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        import json
        value = json.loads(content)
        return value if isinstance(value, dict) else {}
