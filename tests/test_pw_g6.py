# Estensione del Giorno 6: i documenti interni si filtrano anche per filiale, dentro la query.
import pytest
from sqlalchemy import text

from src.db.session import AsyncSessionLocal, engine
from src.services import retrieval_service
from src.services.ingest_service import IngestService
from src.services.retrieval_service import RetrievalService
from tests.finti import embedder_finto, vettore

CANARINO = "Il codice del caveau di Milazzo è glicine-ambra-nove."
DI_MILAZZO = f"# Cassa di Milazzo\n\nProcedura di apertura del caveau della filiale. {CANARINO}"
DI_TUTTI = "# Cassa\n\nProcedura di apertura del caveau, uguale in tutte le filiali della banca."


@pytest.fixture(autouse=True)
def soglia_dei_vettori_finti(monkeypatch: pytest.MonkeyPatch) -> None:
    # I vettori finti hanno un'altra scala rispetto a bge-m3: qui vale la soglia del corso.
    monkeypatch.setattr(retrieval_service, "SOGLIA_PREDEFINITA", 0.35)


async def documenti_visti(role: str, username: str | None) -> set[str]:
    domanda = vettore("procedura di apertura del caveau della filiale")
    async with AsyncSessionLocal() as s:
        trovati = await RetrievalService(s).search_for_user(domanda, role, username)
    return {t.document_id for t in trovati}


async def test_il_documento_di_una_filiale_lo_vede_solo_quella_filiale_e_la_sede():
    from scripts.seed_users import main as seed_utenti

    await engine.dispose()  # toglie dal pool le connessioni dei client di altri test
    async with engine.begin() as c:
        await c.execute(text("TRUNCATE document_chunks, document_branches"))
    await seed_utenti()  # mbianchi a LIP01, fneri a MIL01, grossi in sede centrale
    async with AsyncSessionLocal() as s:
        servizio = IngestService(s, embedder_finto())
        await servizio.ingest("cassa_milazzo", DI_MILAZZO, None, "internal", ["MIL01"])
        await servizio.ingest("cassa_tutti", DI_TUTTI, None, "internal")

    assert await documenti_visti("operator", "fneri") == {"cassa_milazzo", "cassa_tutti"}
    assert await documenti_visti("compliance_lead", "grossi") == {"cassa_milazzo", "cassa_tutti"}
    # un'altra filiale, e un utente che non è nel database, vedono solo il documento di tutti
    assert await documenti_visti("operator", "mbianchi") == {"cassa_tutti"}
    assert await documenti_visti("operator", "fantasma") == {"cassa_tutti"}
