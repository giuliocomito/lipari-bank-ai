# Contratti dell'advisor e dell'ingestione dei documenti.
from typing import Literal

from pydantic import BaseModel, Field


class IngestRequest(BaseModel):
    document_id: str = Field(..., max_length=100)
    content: str = Field(..., min_length=10)
    metadata: dict[str, str] | None = None
    # Solo i livelli che esistono: un nome sbagliato, come «compliance-only», darebbe passaggi
    # che nessun ruolo vede, e il documento sparirebbe senza errori. Così è un 422.
    visibility: Literal["public", "internal", "risk_only", "compliance_only"] = "public"


class IngestResponse(BaseModel):
    chunk_count: int
    embedding_dim: int


class AdviceRequest(BaseModel):
    question: str = Field(..., min_length=5, max_length=1000)


class Citation(BaseModel):
    document_id: str
    chunk_id: str
    excerpt: str
    similarity: float


class AdviceResponse(BaseModel):
    answer: str
    citations: list[Citation]
    tokens_used: int
    cost_eur: float  # la sola generazione: la riscrittura non è contata
    rewritten_query: str | None = None  # quello che il recupero ha cercato davvero
