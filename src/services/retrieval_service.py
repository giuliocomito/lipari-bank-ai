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

    # La stessa query con il filtro sui livelli che il ruolo può vedere e, per i documenti
    # interni, sull'appartenenza alla filiale. Un documento interno senza filiali vale per tutta
    # la banca; uno con filiali lo vede chi lavora in una di esse o chi sta in sede centrale
    # (branch vuoto). Se l'utente non è nel database, la seconda EXISTS è falsa: vede di meno.
    SQL_PER_RUOLO = sql(
        """
        SELECT c.id, c.document_id, c.content,
               1 - (c.embedding <=> CAST(:q AS vector)) AS similarity
        FROM document_chunks AS c
        WHERE 1 - (c.embedding <=> CAST(:q AS vector)) >= :soglia
          AND c.visibility = ANY(:livelli)
          AND (
            c.visibility <> 'internal'
            OR NOT EXISTS (
              SELECT 1 FROM document_branches AS d WHERE d.document_id = c.document_id
            )
            OR EXISTS (
              SELECT 1
              FROM app_users AS u
              LEFT JOIN document_branches AS d
                ON d.document_id = c.document_id AND d.branch = u.branch
              WHERE u.username = :utente AND (u.branch IS NULL OR d.branch IS NOT NULL)
            )
          )
        ORDER BY c.embedding <=> CAST(:q AS vector)
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
        self,
        query_vec: list[float],
        role: str,
        username: str | None = None,
        top_k: int = 5,
        soglia: float | None = None,
    ) -> list[RetrievalResult]:
        """I passaggi più vicini fra quelli che il ruolo e la filiale dell'utente possono vedere.

        Il filtro sta dentro la query, prima dell'ordinamento e del LIMIT: il database non
        restituisce nemmeno i passaggi che l'utente non può vedere. La filiale si legge dal
        database nella stessa query, non dal token. Senza username, dei documenti interni
        restano solo quelli che valgono per tutta la banca.

        L'indice HNSW applica il filtro ai candidati che ha già trovato: se quelli vicini
        appartengono ad altre filiali, la ricerca resterebbe a vuoto pur esistendo passaggi
        visibili (21 domande su 50 nel caso peggiore, con scripts.misura_filiale). Con
        iterative_scan l'indice continua a cercare finché ne trova abbastanza; la modalità
        relaxed_order può invertirne l'ordine, quindi si riordinano per somiglianza.
        """
        await self.session.execute(sql("SET LOCAL hnsw.iterative_scan = relaxed_order"))
        trovati = await self._esegui(
            self.SQL_PER_RUOLO,
            query_vec,
            top_k,
            soglia,
            {"livelli": visible_to(role), "utente": username},
        )
        return sorted(trovati, key=lambda t: t.similarity, reverse=True)

    async def _esegui(
        self,
        query: TextClause,
        query_vec: list[float],
        top_k: int,
        soglia: float | None,
        filtri: dict[str, object] | None = None,
    ) -> list[RetrievalResult]:
        parametri: dict[str, object] = {
            "q": str(query_vec),
            "k": top_k,
            "soglia": SOGLIA_PREDEFINITA if soglia is None else soglia,
            **(filtri or {}),
        }
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
