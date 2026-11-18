from pydantic import BaseModel
from sqlalchemy import text as sql
from sqlalchemy.ext.asyncio import AsyncSession

# Tarata con scripts.misura_soglia su bge-m3 e sulle circolari di data/docs: è la soglia più
# alta che non perde risposte giuste, e ferma 5 domande estranee su 11 in taratura e 3 su 6 in
# verifica (con 0,35 nessuna). Cambiando modello o documenti va rimisurata.
SOGLIA_PREDEFINITA = 0.50


class RetrievalResult(BaseModel):
    chunk_id: str
    document_id: str
    content: str
    similarity: float


class RetrievalService:
    """Ricerca vettoriale sui passaggi dei documenti."""

    # <=> è la distanza del coseno di pgvector; la similarità è 1 meno la distanza
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
        self, query_vec: list[float], top_k: int = 5, soglia: float | None = None
    ) -> list[RetrievalResult]:
        """Restituisce i passaggi più vicini al vettore della domanda, in ordine di vicinanza.

        Riceve il vettore già calcolato, così la stessa ricerca serve qualunque chiamante che lo
        abbia. I passaggi sotto la soglia vengono scartati: una lista vuota dice al chiamante
        che non c'è niente di pertinente, cosa che cinque passaggi irrilevanti non direbbero.
        Senza una soglia esplicita vale SOGLIA_PREDEFINITA, letta al momento della chiamata.
        """
        if soglia is None:
            soglia = SOGLIA_PREDEFINITA
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
