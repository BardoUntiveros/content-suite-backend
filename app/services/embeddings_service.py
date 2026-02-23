from __future__ import annotations

from google import genai
from google.genai import types

from app.core.config import Settings


class EmbeddingService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.google_client = genai.Client(api_key=settings.google_api_key)

    def embed_text(self, text: str) -> list[float]:
        response = self.google_client.models.embed_content(
            model=self.settings.google_embedding_model,
            contents=text,
            config=types.EmbedContentConfig(output_dimensionality=768),
        )
        embedding = self._extract_embedding(response)
        if not embedding:
            raise RuntimeError("Embedding provider returned no embedding")
        return embedding

    def _extract_embedding(self, response: object) -> list[float] | None:
        candidate = getattr(response, "embeddings", None)
        if candidate and isinstance(candidate, list):
            first = candidate[0]
            values = getattr(first, "values", None)
            if values and isinstance(values, list):
                return [float(v) for v in values]

        embedding = getattr(response, "embedding", None)
        if embedding:
            values = getattr(embedding, "values", None)
            if values and isinstance(values, list):
                return [float(v) for v in values]

        return None
