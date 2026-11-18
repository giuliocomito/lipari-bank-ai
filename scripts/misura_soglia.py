"""Misura, per ogni soglia possibile, quante domande senza risposta ferma e quante giuste perde.

È l'estensione del Giorno 5. Indicizza data/docs come scripts.misura_recupero, poi per ogni
domanda di data/eval/recupero_g5.json recupera i primi cinque passaggi senza soglia. Una domanda
con risposta è tenuta se il passaggio del documento giusto supera la soglia; una domanda senza
risposta è fermata se nessun passaggio la supera, e allora il modello non viene chiamato.
I conti sono separati per gruppo: la soglia si sceglie sul gruppo «taratura» e si verifica sul
gruppo «verifica».

    uv run python -m scripts.misura_soglia
"""

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path

from scripts.misura_recupero import indicizza
from src.db.session import AsyncSessionLocal, engine
from src.llm.factory import get_embedder
from src.services.retrieval_service import SOGLIA_PREDEFINITA, RetrievalService

K = 5
SOGLIE = [round(0.35 + i / 100, 2) for i in range(31)]  # da 0,35 a 0,65


@dataclass
class Esito:
    gruppo: str
    con_risposta: bool
    giusta: float  # similarità del passaggio giusto nei primi K, 0 se manca
    migliore: float  # similarità del passaggio più vicino


def conta(esiti: list[Esito], soglia: float) -> tuple[int, int, int, int]:
    """Domande giuste tenute e totali, domande senza risposta fermate e totali."""
    giuste = [e for e in esiti if e.con_risposta]
    estranee = [e for e in esiti if not e.con_risposta]
    tenute = sum(e.giusta >= soglia for e in giuste)
    fermate = sum(e.migliore < soglia for e in estranee)
    return tenute, len(giuste), fermate, len(estranee)


async def main() -> None:
    await indicizza()
    grezzo = await asyncio.to_thread(Path("data/eval/recupero_g5.json").read_text, "utf-8")
    embedder = get_embedder()
    esiti: list[Esito] = []
    for voce in json.loads(grezzo)["domande"]:
        vettore = await embedder.embed_one(voce["domanda"])
        async with AsyncSessionLocal() as s:
            trovati = await RetrievalService(s).search(vettore, top_k=K, soglia=-1.0)
        giusta = next((t.similarity for t in trovati if t.document_id == voce["documento"]), 0.0)
        esiti.append(
            Esito(voce["gruppo"], voce["documento"] is not None, giusta, trovati[0].similarity)
        )
        segno = "con" if voce["documento"] else "senza"
        print(f"  {voce['gruppo']:<9} {segno:<5} {trovati[0].similarity:.3f}  {voce['domanda']}")
    await engine.dispose()

    print("\nsoglia | taratura: giuste tenute, estranee fermate | verifica: idem")
    for soglia in SOGLIE:
        t = conta([e for e in esiti if e.gruppo == "taratura"], soglia)
        v = conta([e for e in esiti if e.gruppo == "verifica"], soglia)
        attuale = "  <- attuale" if soglia == SOGLIA_PREDEFINITA else ""
        print(
            f"  {soglia:.2f} | {t[0]:>2}/{t[1]}  {t[2]:>2}/{t[3]}"
            f" | {v[0]:>2}/{v[1]}  {v[2]:>2}/{v[3]}{attuale}"
        )


if __name__ == "__main__":
    asyncio.run(main())
