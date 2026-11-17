# scripts/misura_recupero.py — quanto spesso il recupero porta il documento giusto
"""La linea di partenza del Project Work G5: il recupero misurato con gli embedding veri.

Indicizza i documenti di data/docs con il modello di embedding della configurazione (bge-m3
su Ollama), poi per ogni domanda di data/eval/recupero_g5.json guarda i primi cinque passaggi
senza soglia: in che posizione compare il documento che contiene la risposta, e con quale
similarità. Per le domande senza risposta nei documenti guarda la similarità del passaggio
più vicino: è quella che la soglia deve tagliare.

    uv run python -m scripts.misura_recupero

Usa il database della configurazione (DATABASE_URL) e scrive nella tabella document_chunks.
"""

import asyncio
import json
from pathlib import Path

from src.db.session import AsyncSessionLocal, engine
from src.llm.factory import get_embedder
from src.services.ingest_service import IngestService
from src.services.retrieval_service import SOGLIA_PREDEFINITA, RetrievalService

K = 5


async def indicizza() -> int:
    totale = 0
    for percorso in sorted(Path("data/docs").glob("*.md")):
        testo = await asyncio.to_thread(percorso.read_text, encoding="utf-8")
        async with AsyncSessionLocal() as s:
            totale += await IngestService(s, get_embedder()).ingest(
                percorso.stem, testo, {"source": str(percorso)}
            )
    return totale


async def main() -> None:
    passaggi = await indicizza()
    dati = json.loads(Path("data/eval/recupero_g5.json").read_text(encoding="utf-8"))
    embedder = get_embedder()
    al_primo = nei_primi_k = con_risposta = 0
    simili_giuste: list[float] = []
    simili_estranee: list[float] = []
    print(f"{passaggi} passaggi indicizzati con {embedder.model}\n")
    for voce in dati["domande"]:
        vettore = await embedder.embed_one(voce["domanda"])
        async with AsyncSessionLocal() as s:
            trovati = await RetrievalService(s).search(vettore, top_k=K, soglia=-1.0)
        documenti = [t.document_id for t in trovati]
        if voce["documento"] is None:
            simili_estranee.append(trovati[0].similarity)
            print(f"  [nessuno] {trovati[0].similarity:.3f}  {voce['domanda']}")
            continue
        con_risposta += 1
        posizione = documenti.index(voce["documento"]) + 1 if voce["documento"] in documenti else 0
        al_primo += posizione == 1
        nei_primi_k += posizione > 0
        if posizione:
            simili_giuste.append(trovati[posizione - 1].similarity)
        print(
            f"  [pos. {posizione or '-'}] {trovati[0].similarity:.3f}  {voce['domanda']}"
            f"  -> {documenti[0]}"
        )
    await engine.dispose()
    print(f"\nIl documento giusto al primo posto: {al_primo} su {con_risposta}")
    print(f"Il documento giusto nei primi {K}: {nei_primi_k} su {con_risposta}")
    print(
        f"Similarità del passaggio giusto: da {min(simili_giuste):.3f} a {max(simili_giuste):.3f}"
    )
    print(
        "Similarità del passaggio più vicino, domande senza risposta: "
        f"da {min(simili_estranee):.3f} a {max(simili_estranee):.3f}"
    )
    passano = sum(s >= SOGLIA_PREDEFINITA for s in simili_estranee)
    print(
        f"Con la soglia del corso ({SOGLIA_PREDEFINITA}): {passano} domande senza risposta su "
        f"{len(simili_estranee)} arrivano comunque al modello"
    )


if __name__ == "__main__":
    asyncio.run(main())
