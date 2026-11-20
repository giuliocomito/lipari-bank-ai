"""Esegue le prove del Project Work G6 sull'indice vero, con i token veri.

Indicizza le circolari di data/docs con bge-m3 su Ollama, ciascuna con il livello e la filiale
presi dalla cartella; gli utenti fanno il login vero e chiamano l'API con il loro token.
Il modello che scrive la risposta è il finto che ripete tutto il contesto ricevuto: se un
passaggio riservato arrivasse al modello, comparirebbe nella risposta. La riscrittura è spenta.
Il database è quello di test, svuotato all'inizio.

    uv run python -m scripts.prove_g6
"""

import asyncio
import logging
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://lipari:lipari@localhost:5432/lipari_ai_test"
)
os.environ.setdefault("JWT_SECRET", "segreto-delle-prove-lungo-almeno-trentadue-caratteri")

import jwt  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from scripts import seed_users  # noqa: E402
from scripts.ingest_docs import livello_e_filiali  # noqa: E402
from src.api.advice import get_rewriter, limiter  # noqa: E402
from src.auth.tokens import ALGORITHM, create_access_token  # noqa: E402
from src.config import settings  # noqa: E402
from src.db.session import AsyncSessionLocal, engine  # noqa: E402
from src.llm.factory import get_embedder, get_llm_provider  # noqa: E402
from src.main import app  # noqa: E402
from src.services.ingest_service import IngestService  # noqa: E402
from tests.finti import ModelloEco, riscrittore_spento  # noqa: E402

CANARINO = "Sono in corso tre istruttorie su controparti ricorrenti"  # solo nel documento riservato
DI_MILAZZO = "si svuota ogni martedì e venerdì alle 7:30"  # solo nel documento della filiale MIL01
RISULTATI: list[tuple[str, bool]] = []


def esito(nome: str, ok: bool, dettaglio: str) -> None:
    RISULTATI.append((nome, ok))
    print(f"{'OK' if ok else 'NO'}  {nome}\n    {dettaglio}\n")


class Registro(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.messaggi: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messaggi.append(record.getMessage())


async def indicizza() -> None:
    docs = Path("data/docs")
    async with engine.begin() as c:
        await c.execute(text("TRUNCATE document_chunks, document_branches"))
    for percorso in sorted(await asyncio.to_thread(lambda: list(docs.rglob("*.md")))):
        livello, filiali = livello_e_filiali(percorso.relative_to(docs))
        testo = await asyncio.to_thread(percorso.read_text, "utf-8")
        async with AsyncSessionLocal() as s:
            await IngestService(s, get_embedder()).ingest(
                percorso.stem, testo, None, livello, filiali
            )


async def token(c: AsyncClient, utente: str) -> str:
    r = await c.post("/api/auth/login", data={"username": utente, "password": "bootcamp"})
    return str(r.json()["access_token"])


async def chiedi(c: AsyncClient, tok: str, domanda: str) -> tuple[int, str, set[str]]:
    r = await c.post(
        "/api/ai/advice", json={"question": domanda}, headers={"Authorization": f"Bearer {tok}"}
    )
    corpo = r.json()
    fonti = {x["document_id"] for x in corpo.get("citations", [])}
    return r.status_code, str(corpo.get("answer", corpo.get("message", ""))), fonti


async def main() -> None:
    await seed_users.main()
    await indicizza()
    print("Indice pronto, con bge-m3\n")
    app.dependency_overrides[get_llm_provider] = ModelloEco
    app.dependency_overrides[get_rewriter] = riscrittore_spento
    limiter.reset()
    registro = Registro()
    logging.getLogger("src.auth.acl").addHandler(registro)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://prove") as c:
        marco, giulia = await token(c, "mbianchi"), await token(c, "grossi")
        francesca = await token(c, "fneri")
        domanda = "Le operazioni verso controparti in Venezuela sono consentite?"
        _, risposta_m, fonti_m = await chiedi(c, marco, domanda)
        _, risposta_g, fonti_g = await chiedi(c, giulia, domanda)
        esito(
            "1. il canarino non arriva a Marco e arriva a Giulia",
            CANARINO not in risposta_m and CANARINO in risposta_g,
            f"Marco: frase assente, fonti {sorted(fonti_m) or 'nessuna'}; "
            f"Giulia: frase presente, fonti {sorted(fonti_g)}",
        )

        alterato = marco[:-3] + ("A" if marco[-3] != "A" else "B") + marco[-2:]
        stato, messaggio, _ = await chiedi(c, alterato, domanda)
        esito(
            "2. un token alterato di un carattere è respinto",
            (stato, messaggio) == (401, "Token non valido"),
            f"{stato} «{messaggio}»",
        )

        scaduto = jwt.encode(
            {
                "sub": "mbianchi",
                "role": "operator",
                "exp": datetime.now(UTC) - timedelta(minutes=1),
            },
            settings.jwt_secret,
            algorithm=ALGORITHM,
        )
        stato, messaggio, _ = await chiedi(c, scaduto, domanda)
        esito(
            "3. un token scaduto è respinto, con un messaggio diverso",
            (stato, messaggio) == (401, "Token scaduto"),
            f"{stato} «{messaggio}»",
        )

        stagista = create_access_token("mbianchi", "stagista")
        _, _, fonti_s = await chiedi(c, stagista, "Come si gestisce un reclamo allo sportello?")
        _, _, fonti_o = await chiedi(c, marco, "Come si gestisce un reclamo allo sportello?")
        esito(
            "4. un ruolo sconosciuto vede solo il pubblico e finisce nel log",
            "procedura_reclami" not in fonti_s
            and "procedura_reclami" in fonti_o
            and "ruolo_sconosciuto" in registro.messaggi,
            f"stagista: fonti {sorted(fonti_s) or 'nessuna'}; operatore: fonti {sorted(fonti_o)}; "
            f"log {registro.messaggi.count('ruolo_sconosciuto')} volte «ruolo_sconosciuto»",
        )

        cassa = "Quando si svuota la cassa continua di Milazzo?"
        _, risposta_f, fonti_f = await chiedi(c, francesca, cassa)
        _, risposta_m, fonti_m = await chiedi(c, marco, cassa)
        esito(
            "5. estensione: il documento della filiale MIL01 lo vede solo quella filiale",
            DI_MILAZZO in risposta_f and DI_MILAZZO not in risposta_m,
            f"Francesca (MIL01): fonti {sorted(fonti_f)}; "
            f"Marco (LIP01): fonti {sorted(fonti_m) or 'nessuna'}",
        )

    await engine.dispose()
    print(f"{sum(ok for _, ok in RISULTATI)}/{len(RISULTATI)} prove superate")


if __name__ == "__main__":
    asyncio.run(main())
