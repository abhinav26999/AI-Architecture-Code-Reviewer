import logging
import httpx
from typing import List, Optional
from app.core.config import settings

logger = logging.getLogger(__name__)


class EmbeddingClient:
    async def get_embedding(self, text: str) -> List[float]:
        """
        Generates vector embeddings for a given text segment.
        Toggles between local Ollama and mock/cloud depending on settings.
        """
        if settings.EMBEDDING_PROVIDER == "ollama":
            return await self._get_ollama_embedding(text)
        else:
            # Fallback to mock zero-vector for testing if provider not found/active
            logger.warning(f"Unsupported embedding provider '{settings.EMBEDDING_PROVIDER}'. Returning mock zero vector.")
            return [0.0] * 768

    async def _get_ollama_embedding(self, text: str) -> List[float]:
        """Requests vector embedding from local Ollama instance."""
        payload = {
            "model": settings.OLLAMA_EMBED_MODEL,
            "prompt": text
        }
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    settings.OLLAMA_EMBED_URL,
                    json=payload,
                    timeout=10.0
                )
                
                if response.status_code == 200:
                    data = response.json()
                    # Ollama return format: {"embedding": [0.1, 0.2, ...]}
                    if "embedding" in data:
                        return data["embedding"]
                    elif "embeddings" in data and len(data["embeddings"]) > 0:
                        return data["embeddings"][0]
                    else:
                        raise ValueError(f"Ollama response missing embedding vector: {data}")
                else:
                    raise httpx.HTTPStatusError(
                        f"Ollama returned status code {response.status_code}",
                        request=response.request,
                        response=response
                    )
        except Exception as e:
            logger.error(f"Failed to fetch embedding from Ollama: {e}")
            # Instead of crashing the pipeline, we fallback gracefully to a mock vector
            # so the system remains resilient during local runs if Ollama is not booted.
            logger.info("Falling back to mock 768-dimension vector.")
            return [0.0] * 768


# Singleton instance
embedding_client = EmbeddingClient()
