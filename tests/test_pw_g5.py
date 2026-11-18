# Estensione del Giorno 5: la soglia tarata su bge-m3 ferma le domande lontane dai documenti.
import math

from sqlalchemy import text

from src.db.models import DIMENSIONI_EMBEDDING, DocumentChunk
from src.db.session import AsyncSessionLocal, engine
from src.services.rag_service import RIFIUTO, RAGService
from src.services.retrieval_service import RetrievalService
from src.types.advice import AdviceRequest
from tests.finti import ModelloFisso


def a_somiglianza(coseno: float) -> list[float]:
    """Vettore unitario con la similarità del coseno indicata rispetto al primo asse."""
    v = [0.0] * DIMENSIONI_EMBEDDING
    v[0], v[1] = coseno, math.sqrt(1 - coseno**2)
    return v


class EmbedderFisso:
    """Restituisce sempre lo stesso vettore, qualunque sia la domanda."""

    def __init__(self, vettore: list[float]) -> None:
        self.vettore = vettore

    async def embed_one(self, testo: str) -> list[float]:
        return self.vettore


async def chiedi(coseno: float) -> tuple[str, int]:
    modello = ModelloFisso("Il bonifico istantaneo costa €1.00 [fonte-1].")
    async with AsyncSessionLocal() as s:
        embedder = EmbedderFisso(a_somiglianza(coseno))
        servizio = RAGService(RetrievalService(s), embedder, modello, "PROMPT")
        esito = await servizio.advise(AdviceRequest(question="una domanda qualsiasi"))
    return esito.answer, len(modello.ricevuti)


async def test_una_domanda_a_somiglianza_045_non_arriva_al_modello():
    """Con la soglia del corso, 0,35, passerebbe; con quella tarata, 0,50, si ferma."""
    async with engine.begin() as c:
        await c.execute(text("TRUNCATE document_chunks"))
    async with AsyncSessionLocal() as s:
        s.add(
            DocumentChunk(
                document_id="commissioni_bonifico",
                chunk_index=0,
                content="Bonifico istantaneo SEPA: costo €1.00.",
                embedding=a_somiglianza(1.0),
                chunk_metadata={},
            )
        )
        await s.commit()

    assert await chiedi(0.45) == (RIFIUTO, 0)
    risposta, chiamate = await chiedi(0.55)
    assert risposta != RIFIUTO and chiamate == 1
