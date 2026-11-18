# Project Work del Giorno 3: le proprietà dichiarate e i test che le verificano.
from collections.abc import AsyncIterator
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession

from scripts import seed_accounts
from src.db.models import Movement
from src.db.repos import AccountRepository, ChatRepository
from src.db.session import AsyncSessionLocal, engine
from tests.test_g3 import client, conta, periodo, tabelle_vuote  # noqa: F401 (fixture autouse)

PRINCIPALE = seed_accounts.PRINCIPALE
SALDO_INIZIALE = Decimal("48200.00")


async def saldo(account_id: str) -> Decimal:
    async with AsyncSessionLocal() as s:
        q = text("SELECT balance FROM accounts WHERE id = :id")
        return Decimal((await s.execute(q, {"id": account_id})).scalar_one())


def movimento(importo: str) -> dict[str, str]:
    return {"booking_date": str(date.today()), "description": "Prova", "amount": importo}


# Estensione
async def test_movimento_e_saldo_insieme_o_per_niente(monkeypatch: pytest.MonkeyPatch):
    """Movimento e saldo vengono scritti insieme, oppure nessuno dei due."""
    await seed_accounts.main()
    movimenti = await conta("movements")

    async with client() as c:
        ok = await c.post(f"/api/ai/accounts/{PRINCIPALE}/movements", json=movimento("-50.00"))
    assert ok.status_code == 201 and Decimal(ok.json()["balance"]) == Decimal("48150.00")
    assert await conta("movements") == movimenti + 1 and await saldo(PRINCIPALE) == Decimal(
        "48150.00"
    )

    # Il saldo fallisce dopo il flush del movimento nella stessa transazione
    async def saldo_che_fallisce(self: AccountRepository, account_id: str, amount: Decimal) -> None:
        raise RuntimeError("il database cade fra il movimento e il saldo")

    monkeypatch.setattr(AccountRepository, "apply", saldo_che_fallisce)
    async with client(raise_app_exceptions=False) as c:
        ko = await c.post(f"/api/ai/accounts/{PRINCIPALE}/movements", json=movimento("-70.00"))
    assert ko.status_code == 500
    # movimenti e saldo restano quelli di prima della richiesta fallita
    assert await conta("movements") == movimenti + 1
    assert await saldo(PRINCIPALE) == Decimal("48150.00")


# Decisione sul commit
async def test_un_commit_che_fallisce_arriva_al_client(monkeypatch: pytest.MonkeyPatch):
    """Con il commit nel service, un commit fallito arriva al client come errore 500."""
    await seed_accounts.main()
    movimenti = await conta("movements")

    async def commit_rifiutato(self: AsyncSession) -> None:
        raise RuntimeError("il database rifiuta la conferma")

    monkeypatch.setattr(AsyncSession, "commit", commit_rifiutato)
    async with client(raise_app_exceptions=False) as c:
        r = await c.post(f"/api/ai/accounts/{PRINCIPALE}/movements", json=movimento("-10.00"))
    assert r.status_code == 500 and r.json()["error"] == "INTERNAL_ERROR"
    assert await conta("movements") == movimenti and await saldo(PRINCIPALE) == SALDO_INIZIALE


async def test_l_alternativa_scartata_il_commit_dopo_lo_yield(monkeypatch: pytest.MonkeyPatch):
    """Mostra perché il commit non sta in get_db.

    Per default il codice dopo lo yield viene eseguito quando la risposta è già partita.
    """

    async def get_db_che_conferma() -> AsyncIterator[AsyncSession]:
        async with AsyncSessionLocal() as s:
            yield s
            await s.commit()  # la richiesta intera come unità di lavoro

    prova = FastAPI()

    @prova.post("/default")
    async def scope_default(
        s: Annotated[AsyncSession, Depends(get_db_che_conferma)],
    ) -> dict[str, str]:
        return {"id": (await ChatRepository(s).create_session("prova")).id}

    @prova.post("/function")
    async def scope_function(
        s: Annotated[AsyncSession, Depends(get_db_che_conferma, scope="function")],
    ) -> dict[str, str]:
        return {"id": (await ChatRepository(s).create_session("prova")).id}

    async def commit_rifiutato(self: AsyncSession) -> None:
        raise RuntimeError("il database rifiuta la conferma")

    monkeypatch.setattr(AsyncSession, "commit", commit_rifiutato)
    trasporto = ASGITransport(app=prova, raise_app_exceptions=False)
    async with AsyncClient(transport=trasporto, base_url="http://test") as c:
        default = await c.post("/default")
        function = await c.post("/function")
    assert default.status_code == 200  # il client riceve l'id di una conversazione mai salvata
    assert function.status_code == 500  # con scope="function" il fallimento arriva al client
    assert await conta("chat_sessions") == 0


# Prova del centesimo
async def test_il_centesimo_regge_e_i_tre_decimali_non_passano():
    await seed_accounts.main()
    oggi = date.today()
    # commissioni aggiunte a quelle del seed, con valori che in virgola mobile non tornano
    commissioni = [Decimal("-0.10"), Decimal("-0.20"), Decimal("-0.30"), Decimal("-0.01")] * 15
    # quattro importi con tre decimali, scritti con l'ORM perché l'API li rifiuterebbe
    tre_decimali = [Decimal("-12.345"), Decimal("-0.105"), Decimal("-7.999"), Decimal("-0.005")]
    async with AsyncSessionLocal() as s:
        s.add_all(
            Movement(
                account_id=PRINCIPALE,
                booking_date=oggi - timedelta(days=1 + i % 60),
                description="Commissione di prova",
                amount=a,
            )
            for i, a in enumerate(commissioni + tre_decimali)
        )
        await s.commit()

    async with client() as c:
        r = await c.get(f"/api/ai/accounts/{PRINCIPALE}/spending", params=periodo())
    totale = Decimal(r.json()["total"])

    uscite_seed = [-a for i, _, _, a in seed_accounts.MOVIMENTI if i == PRINCIPALE and a < 0]
    centesimo = Decimal("0.01")
    al_centesimo = [-a.quantize(centesimo, rounding=ROUND_HALF_UP) for a in tre_decimali]
    attesa = sum(uscite_seed + [-a for a in commissioni] + al_centesimo, Decimal("0"))
    assert totale == attesa  # ricalcolata dal test, al centesimo
    # il database ha arrotondato i tre decimali in scrittura (12.345 è diventato 12.35)
    assert totale != sum(uscite_seed + [-a for a in commissioni + tre_decimali], Decimal("0"))

    # L'API invece rifiuta un importo con tre decimali prima che arrivi al database
    async with client() as c:
        no = await c.post(f"/api/ai/accounts/{PRINCIPALE}/movements", json=movimento("-12.345"))
        zero = await c.post(f"/api/ai/accounts/{PRINCIPALE}/movements", json=movimento("0.00"))
    assert no.status_code == 422 and no.json()["error"] == "VALIDATION_ERROR"
    assert zero.status_code == 422


# Conversazione lunga
async def query_di_una_chat(messaggi_precedenti: int) -> int:
    """Conta le query SQL di una POST /chat su una conversazione che ha già N messaggi."""
    async with AsyncSessionLocal() as s:
        repo = ChatRepository(s)
        chat = await repo.create_session(user_id="mbianchi")  # l'operatore della chat dal G4
        for i in range(messaggi_precedenti):
            await repo.add_message(chat.id, "user", f"messaggio {i}")
        await s.commit()

    query: list[str] = []

    def registra(*args: object) -> None:
        query.append(str(args[2]))

    event.listen(engine.sync_engine, "before_cursor_execute", registra)
    try:
        async with client() as c:
            r = await c.post("/api/ai/chat", json={"session_id": chat.id, "message": "ancora"})
        assert r.status_code == 200
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", registra)
    return len(query)


async def test_la_chat_non_cresce_coi_messaggi():
    corta, lunga = await query_di_una_chat(2), await query_di_una_chat(200)
    assert corta == lunga  # stesso numero di query con 2 e con 200 messaggi: niente N+1
