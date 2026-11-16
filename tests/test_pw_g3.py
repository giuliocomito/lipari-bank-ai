# tests/test_pw_g3.py — il Project Work del Giorno 3: le proprietà dichiarate, e le loro prove
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
from tests.test_g3 import client, conta, periodo, tabelle_vuote  # noqa: F401 — la stessa fixture

PRINCIPALE = seed_accounts.PRINCIPALE
SALDO_INIZIALE = Decimal("48200.00")


async def saldo(account_id: str) -> Decimal:
    async with AsyncSessionLocal() as s:
        q = text("SELECT balance FROM accounts WHERE id = :id")
        return Decimal((await s.execute(q, {"id": account_id})).scalar_one())


def movimento(importo: str) -> dict[str, str]:
    return {"booking_date": str(date.today()), "description": "Prova", "amount": importo}


# ------------------------------------------------------------------ l'estensione
async def test_movimento_e_saldo_insieme_o_per_niente(monkeypatch: pytest.MonkeyPatch):
    """La proprietà dell'estensione: movimento e saldo si scrivono insieme, o nessuno dei due."""
    await seed_accounts.main()
    movimenti = await conta("movements")

    async with client() as c:
        ok = await c.post(f"/api/ai/accounts/{PRINCIPALE}/movements", json=movimento("-50.00"))
    assert ok.status_code == 201 and Decimal(ok.json()["balance"]) == Decimal("48150.00")
    assert await conta("movements") == movimenti + 1 and await saldo(PRINCIPALE) == Decimal(
        "48150.00"
    )

    # Ora il saldo fallisce dopo che il movimento è già stato scritto (flush) nella transazione
    async def saldo_che_fallisce(self: AccountRepository, account_id: str, amount: Decimal) -> None:
        raise RuntimeError("il database cade fra il movimento e il saldo")

    monkeypatch.setattr(AccountRepository, "apply", saldo_che_fallisce)
    async with client(raise_app_exceptions=False) as c:
        ko = await c.post(f"/api/ai/accounts/{PRINCIPALE}/movements", json=movimento("-70.00"))
    assert ko.status_code == 500
    # né il movimento da solo, né il saldo: tutto come prima della richiesta fallita
    assert await conta("movements") == movimenti + 1
    assert await saldo(PRINCIPALE) == Decimal("48150.00")


# ------------------------------------------------------------------ la decisione
async def test_un_commit_che_fallisce_arriva_al_client(monkeypatch: pytest.MonkeyPatch):
    """Il commit sta nel service: se fallisce, il client riceve un errore, non un 201."""
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
    """Perché il commit non sta in get_db: dopo lo yield, per default, la risposta è già partita."""

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
    assert default.status_code == 200  # il client ha un id per una conversazione che non c'è
    assert function.status_code == 500  # con scope="function" il fallimento arriva al client
    assert await conta("chat_sessions") == 0


# ------------------------------------------------------------------ la prova del centesimo
async def test_il_centesimo_regge_e_i_tre_decimali_non_passano():
    await seed_accounts.main()
    oggi = date.today()
    # le mie commissioni, in aggiunta a quelle del seed: i valori che in virgola mobile non tornano
    commissioni = [Decimal("-0.10"), Decimal("-0.20"), Decimal("-0.30"), Decimal("-0.01")] * 15
    # e quattro importi con tre decimali, scritti dall'ORM senza passare dall'API
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
    assert totale == attesa  # la somma fatta a mano, al centesimo
    # i tre decimali li ha arrotondati il database mentre li scriveva: 12.345 è diventato 12.35
    assert totale != sum(uscite_seed + [-a for a in commissioni + tre_decimali], Decimal("0"))

    # Dall'API, invece, un importo con tre decimali non arriva al database: si rifiuta
    async with client() as c:
        no = await c.post(f"/api/ai/accounts/{PRINCIPALE}/movements", json=movimento("-12.345"))
        zero = await c.post(f"/api/ai/accounts/{PRINCIPALE}/movements", json=movimento("0.00"))
    assert no.status_code == 422 and no.json()["error"] == "VALIDATION_ERROR"
    assert zero.status_code == 422


# ------------------------------------------------------------------ la conversazione lunga
async def query_di_una_chat(messaggi_precedenti: int) -> int:
    """Quante istruzioni SQL fa una POST /chat su una conversazione che ne ha già N."""
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
    assert corta == lunga  # le stesse query con 2 messaggi e con 200: niente N+1
