from __future__ import annotations

from math import sqrt

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import RAG_CHUNK_SCOPE_FIELD, RagChunk
from app.services.embeddings_service import EmbeddingService


class RagService:
    def __init__(self, embedding_service: EmbeddingService):
        self.embedding_service = embedding_service

    def index_content(
        self,
        db: Session,
        *,
        scope_id: str,
        content_text: str,
        max_chunk_chars: int = 700,
        separator: str = "\n\n",
    ) -> None:
        chunks = self.chunk_text(
            content_text,
            max_chars=max_chunk_chars,
            separator=separator,
        )

        scope_payload_key = RAG_CHUNK_SCOPE_FIELD

        for index, chunk_text in enumerate(chunks):
            embedding = self.embedding_service.embed_text(chunk_text)
            db.add(
                RagChunk(
                    **{
                        scope_payload_key: scope_id,
                    },
                    chunk_index=index,
                    chunk_text=chunk_text,
                    embedding=embedding,
                )
            )

    def retrieve_relevant_chunks(
        self,
        db: Session,
        *,
        scope_id: str,
        query_text: str,
        top_k: int = 4,
    ) -> list[str]:
        query_embedding = self.embedding_service.embed_text(query_text)

        scope_column = getattr(RagChunk, RAG_CHUNK_SCOPE_FIELD)

        if db.bind and db.bind.dialect.name == "postgresql":
            query = (
                select(RagChunk)
                .where(scope_column == scope_id)
                .order_by(RagChunk.embedding.cosine_distance(query_embedding))
                .limit(top_k)
            )
            return [row.chunk_text for row in db.scalars(query).all()]

        chunks = db.scalars(select(RagChunk).where(scope_column == scope_id)).all()

        ranked_chunks = sorted(
            chunks,
            key=lambda chunk: self._cosine_distance(chunk.embedding, query_embedding),
        )

        return [chunk.chunk_text for chunk in ranked_chunks[:top_k]]

    @staticmethod
    def chunk_text(
        content_text: str, *, max_chars: int = 700, separator: str = "\n\n"
    ) -> list[str]:
        parts = [part.strip() for part in content_text.split(separator) if part.strip()]
        chunks: list[str] = []
        current = ""

        for part in parts:
            chunk_piece = f"{separator}{part}".strip()
            candidate = (
                f"{current}\n\n{chunk_piece}".strip() if current else chunk_piece
            )
            if len(candidate) <= max_chars:
                current = candidate
                continue
            if current:
                chunks.append(current)
            current = chunk_piece

        if current:
            chunks.append(current)

        return chunks or [content_text]

    @staticmethod
    def _cosine_distance(a: list[float], b: list[float]) -> float:
        numerator = sum(x * y for x, y in zip(a, b, strict=False))
        norm_a = sqrt(sum(x * x for x in a)) or 1.0
        norm_b = sqrt(sum(y * y for y in b)) or 1.0
        cosine_similarity = numerator / (norm_a * norm_b)
        return 1.0 - cosine_similarity
