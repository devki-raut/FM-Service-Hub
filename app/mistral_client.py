import asyncio
import os
from pathlib import Path

import httpx
from mistralai import Mistral

from app.config import get_settings


class MistralService:
    def __init__(self) -> None:
        settings = get_settings()
        self._settings = settings
        self._llm_provider = settings.llm_provider.lower().strip()
        self._embedding_provider = settings.embedding_provider.lower().strip()
        self._embedding_model = None

        if self._llm_provider == "azure_foundry":
            if not settings.azure_foundry_endpoint or not settings.azure_foundry_api_key:
                raise RuntimeError("AZURE_FOUNDRY_ENDPOINT and AZURE_FOUNDRY_API_KEY are required")
            self._client = None
            return

        if not settings.mistral_api_key:
            raise RuntimeError("MISTRAL_API_KEY is required")
        self._client = Mistral(api_key=settings.mistral_api_key)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if self._embedding_provider == "fastembed":
            return await asyncio.to_thread(self._fastembed, texts)

        if self._embedding_provider == "azure_foundry":
            return await self._azure_foundry_embed(texts)

        response = await asyncio.to_thread(
            self._client.embeddings.create,
            model=self._settings.mistral_embedding_model,
            inputs=texts,
        )
        return [item.embedding for item in response.data]

    async def complete(self, messages: list[dict]) -> str:
        if self._llm_provider == "azure_foundry":
            return await self._azure_foundry_complete(messages)

        response = await asyncio.to_thread(
            self._client.chat.complete,
            model=self._settings.mistral_chat_model,
            messages=messages,
            temperature=0.1,
        )
        return response.choices[0].message.content or ""

    def _fastembed(self, texts: list[str]) -> list[list[float]]:
        os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
        from fastembed import TextEmbedding

        if self._embedding_model is None:
            cache_dir = Path(self._settings.fastembed_cache_dir).resolve()
            cache_dir.mkdir(parents=True, exist_ok=True)
            self._embedding_model = TextEmbedding(
                model_name=self._settings.fastembed_model,
                cache_dir=str(cache_dir),
            )
        return [embedding.tolist() for embedding in self._embedding_model.embed(texts)]

    async def _azure_foundry_embed(self, texts: list[str]) -> list[list[float]]:
        model = self._settings.azure_foundry_embedding_model.strip()
        if not model:
            raise RuntimeError("AZURE_FOUNDRY_EMBEDDING_MODEL is required when EMBEDDING_PROVIDER=azure_foundry")

        payload: dict = {"input": texts, "model": model}
        response = await self._azure_foundry_post("/models/embeddings", payload)
        return [item["embedding"] for item in response["data"]]

    async def _azure_foundry_complete(self, messages: list[dict]) -> str:
        model = self._settings.azure_foundry_chat_model.strip()
        if not model:
            raise RuntimeError("AZURE_FOUNDRY_CHAT_MODEL is required when LLM_PROVIDER=azure_foundry")

        payload: dict = {"messages": messages, "temperature": 0.1, "model": model}
        response = await self._azure_foundry_post("/models/chat/completions", payload)
        return response["choices"][0]["message"].get("content") or ""

    async def _azure_foundry_post(self, path: str, payload: dict) -> dict:
        endpoint = self._settings.azure_foundry_endpoint.rstrip("/")
        url = f"{endpoint}{path}"
        headers = {
            "Content-Type": "application/json",
            "api-key": self._settings.azure_foundry_api_key,
        }
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(url, headers=headers, json=payload)
            if response.is_error:
                body = response.text[:2000]
                raise RuntimeError(f"Azure Foundry request failed: {response.status_code} {response.reason_phrase}: {body}")
            return response.json()

