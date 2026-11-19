"""Esegue le quattro prove della prima mezz'ora del Project Work G5, sull'indice vero.

I passaggi sono vettorizzati da bge-m3 su Ollama, come in produzione; il database è quello di
test, svuotato all'inizio. Il modello linguistico non serve: nelle prove che arrivano fino alla
risposta la domanda viene fermata dalla soglia prima di raggiungerlo.

    uv run python -m scripts.prove_g5
"""

import asyncio
import os
from pathlib import Path

os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://lipari:lipari@localhost:5432/lipari_ai_test"
)
os.environ.setdefault("JWT_SECRET", "segreto-delle-prove-lungo-almeno-trentadue-caratteri")

from sqlalchemy import func, select, text  # noqa: E402

from scripts.misura_recupero import indicizza  # noqa: E402
from src.auth.deps import UserContext  # noqa: E402
from src.db.models import DocumentChunk  # noqa: E402
from src.db.session import AsyncSessionLocal, engine  # noqa: E402
from src.llm.factory import get_embedder  # noqa: E402
from src.llm.rewriter import QueryRewriter  # noqa: E402
from src.services.ingest_service import IngestService  # noqa: E402
from src.services.rag_service import RIFIUTO, RAGService  # noqa: E402
from src.services.retrieval_service import (  # noqa: E402
    SOGLIA_PREDEFINITA,
    RetrievalResult,
    RetrievalService,
)
from tests.finti import ModelloFisso  # noqa: E402

COMMISSIONI = Path("data/docs/commissioni_bonifico.md")
RISULTATI: list[tuple[str, bool]] = []


def esito(nome: str, ok: bool, dettaglio: str) -> None:
    RISULTATI.append((nome, ok))
    print(f"{'OK' if ok else 'NO'}  {nome}\n    {dettaglio}\n")


async def passaggi(document_id: str) -> int:
    async with AsyncSessionLocal() as s:
        quanti = await s.scalar(
            select(func.count()).where(DocumentChunk.document_id == document_id)
        )
        return int(quanti or 0)


async def cerca(domanda: str) -> list[RetrievalResult]:
    vettore = await get_embedder().embed_one(domanda)
    async with AsyncSessionLocal() as s:
        return await RetrievalService(s).search(vettore)


async def ingerisci(document_id: str, testo: str) -> int:
    async with AsyncSessionLocal() as s:
        return await IngestService(s, get_embedder()).ingest(document_id, testo)


def doppioni(trovati: list[RetrievalResult]) -> int:
    return len(trovati) - len({(t.document_id, t.content) for t in trovati})


async def main() -> None:
    async with engine.begin() as c:
        await c.execute(text("TRUNCATE document_chunks"))
    await indicizza()
    testo = await asyncio.to_thread(COMMISSIONI.read_text, "utf-8")
    print(f"Indice pronto, soglia {SOGLIA_PREDEFINITA}\n")

    domanda = "Come si apre un deposito titoli?"
    modello = ModelloFisso("non dovrebbe servire")
    async with AsyncSessionLocal() as s:
        spento = QueryRewriter(modello, "", enabled=False)
        servizio = RAGService(RetrievalService(s), get_embedder(), modello, spento, "PROMPT")
        risposta = await servizio.advise(domanda, UserContext(username="mbianchi", role="operator"))
    esito(
        "1. una domanda estranea riceve il rifiuto, senza citazioni",
        risposta.answer == RIFIUTO and not risposta.citations and not modello.ricevuti,
        f"«{domanda}»: {risposta.answer!r}, citazioni {len(risposta.citations)}, "
        f"chiamate al modello {len(modello.ricevuti)}",
    )

    prima = await passaggi(COMMISSIONI.stem)
    await ingerisci(COMMISSIONI.stem, testo)
    dopo = await passaggi(COMMISSIONI.stem)
    trovati = await cerca("Quanto costa un bonifico SEPA allo sportello?")
    esito(
        "2. lo stesso documento caricato due volte non raddoppia le citazioni",
        prima == dopo and doppioni(trovati) == 0,
        f"passaggi del documento prima {prima}, dopo {dopo}; "
        f"{len(trovati)} recuperati, doppioni {doppioni(trovati)}",
    )

    unito = await ingerisci("pdf_unito_a_mano", testo + "\n\n" + testo)
    trovati = await cerca("Quanto costa un bonifico estero fuori dall'area SEPA?")
    dal_pdf = [t for t in trovati if t.document_id == "pdf_unito_a_mano"]
    esito(
        "3. la pagina ripetuta non produce due citazioni identiche",
        unito == dopo and doppioni(dal_pdf) == 0,
        f"il documento con la pagina doppia dà {unito} passaggi, come l'originale ({dopo}); "
        f"recuperati da lì {len(dal_pdf)}, doppioni {doppioni(dal_pdf)}",
    )

    vaga = "bonifico costi"
    trovati = await cerca(vaga)
    elenco = ", ".join(f"{t.document_id} {t.similarity:.3f}" for t in trovati) or "nessuno"
    esito(
        "4. una domanda vaga non recupera passaggi che parlano d'altro",
        all(t.document_id in (COMMISSIONI.stem, "pdf_unito_a_mano") for t in trovati),
        f"«{vaga}»: {elenco}",
    )

    await engine.dispose()
    print(f"{sum(ok for _, ok in RISULTATI)}/{len(RISULTATI)} prove superate")


if __name__ == "__main__":
    asyncio.run(main())
