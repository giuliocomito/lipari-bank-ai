# Contratti dell'advisor e dell'ingestione dei documenti.
from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator


class IngestRequest(BaseModel):
    document_id: str = Field(..., max_length=100)
    content: str = Field(..., min_length=10)
    metadata: dict[str, str] | None = None
    # Solo i livelli che esistono: un nome sbagliato, come «compliance-only», darebbe passaggi
    # che nessun ruolo vede, e il documento sparirebbe senza errori. Così è un 422.
    visibility: Literal["public", "internal", "risk_only", "compliance_only"] = "public"
    # Estensione del Giorno 6: le filiali a cui appartiene un documento interno. Vuoto, il
    # documento vale per tutta la banca.
    branches: list[Annotated[str, Field(pattern=r"^[A-Z0-9]{2,16}$")]] = Field(
        default_factory=list, max_length=50
    )

    @model_validator(mode="after")
    def filiali_solo_per_interni(self) -> "IngestRequest":
        if self.branches and self.visibility != "internal":
            raise ValueError("le filiali si assegnano solo ai documenti internal")
        return self


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
