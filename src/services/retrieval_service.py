from pydantic import BaseModel
from sqlalchemy import TextClause
from sqlalchemy import text as sql
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.acl import visible_to

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

    # La stessa query con una riga in più, il filtro sui livelli che il ruolo può vedere.
    SQL_PER_RUOLO = sql(
        """
        SELECT id, document_id, content,
               1 - (embedding <=> CAST(:q AS vector)) AS similarity
        FROM document_chunks
        WHERE 1 - (embedding <=> CAST(:q AS vector)) >= :soglia
          AND visibility = ANY(:livelli)
        ORDER BY embedding <=> CAST(:q AS vector)
        LIMIT :k
        """
    )

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def search(
        self, query_vec: list[float], top_k: int = 5, soglia: float | None = None
    ) -> list[RetrievalResult]:
        """Restituisce i passaggi più vicini al vettore, senza filtro di visibilità.

        Serve agli script e alle misure, dove non c'è un utente. Un percorso che parte da una
        richiesta HTTP deve usare search_for_user, che applica i permessi del ruolo.

        Riceve il vettore già calcolato, così la stessa ricerca serve qualunque chiamante che lo
        abbia. I passaggi sotto la soglia vengono scartati: una lista vuota dice al chiamante
        che non c'è niente di pertinente, cosa che cinque passaggi irrilevanti non direbbero.
        Senza una soglia esplicita vale SOGLIA_PREDEFINITA, letta al momento della chiamata.
        """
        return await self._esegui(self.SQL, query_vec, top_k, soglia)

    async def search_for_user(
        self, query_vec: list[float], role: str, top_k: int = 5, soglia: float | None = None
    ) -> list[RetrievalResult]:
        """I passaggi più vicini fra quelli che il ruolo può vedere.

        Il filtro sta dentro la query, prima dell'ordinamento e del LIMIT: il database non
        restituisce nemmeno i passaggi che il ruolo non può vedere.
        """
        return await self._esegui(
            self.SQL_PER_RUOLO, query_vec, top_k, soglia, livelli=visible_to(role)
        )

    async def _esegui(
        self,
        query: TextClause,
        query_vec: list[float],
        top_k: int,
        soglia: float | None,
        livelli: list[str] | None = None,
    ) -> list[RetrievalResult]:
        parametri: dict[str, object] = {
            "q": str(query_vec),
            "k": top_k,
            "soglia": SOGLIA_PREDEFINITA if soglia is None else soglia,
        }
        if livelli is not None:
            parametri["livelli"] = livelli
        righe = await self.session.execute(query, parametri)
        return [
            RetrievalResult(
                chunk_id=str(r.id),
                document_id=r.document_id,
                content=r.content,
                similarity=float(r.similarity),
            )
            for r in righe
        ]
