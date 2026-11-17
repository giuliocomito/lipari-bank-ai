# src/services/retrieval_service.py — la ricerca vettoriale sui passaggi dei documenti
from pydantic import BaseModel
from sqlalchemy import text as sql
from sqlalchemy.ext.asyncio import AsyncSession

# da tarare sui propri documenti e sul proprio modello di embedding: non è un numero universale
SOGLIA_PREDEFINITA = 0.35


class RetrievalResult(BaseModel):
    chunk_id: str
    document_id: str
    content: str
    similarity: float


class RetrievalService:
    """La ricerca vettoriale sui passaggi dei documenti."""

    # <=> è la distanza del coseno di pgvector: 1 meno la distanza è la similarità
    SQL = sql(
        """
        SELECT id, document_id, content,
               1 - (embedding <=> CAST(:q AS vector)) AS similarity
        FROM document_chunks
        WHERE 1 - (embedding <=> CAST(:q AS vector)) >= :soglia
        ORDER BY embedding <=> CAST(:q AS vector)
        LIMIT :k
        """
    )

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def search(
        self, query_vec: list[float], top_k: int = 5, soglia: float = SOGLIA_PREDEFINITA
    ) -> list[RetrievalResult]:
        """I passaggi più vicini al vettore della domanda, dal più vicino.

        Prende il vettore, non la domanda: vettorizzare è compito di chi chiama, e così la
        stessa ricerca serve chiunque abbia già il vettore.

        Sotto la soglia non torna niente: una lista vuota è una risposta, e il chiamante
        deve poterla distinguere da cinque passaggi irrilevanti.
        """
        righe = await self.session.execute(
            self.SQL, {"q": str(query_vec), "k": top_k, "soglia": soglia}
        )
        return [
            RetrievalResult(
                chunk_id=str(r.id),
                document_id=r.document_id,
                content=r.content,
                similarity=float(r.similarity),
            )
            for r in righe
        ]
