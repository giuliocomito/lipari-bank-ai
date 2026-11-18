"""Verifica che cosa resta nel database se il processo muore fra due scritture.

Lavora sul database di sviluppo:

    uv run python -m scripts.prova_interruzione

Le richieste che scrivono due volte sono la chat (messaggio dell'utente, poi risposta) e il
movimento (movimento, poi saldo). Per ciascuna lo script avvia il server vero in un processo
figlio, con una pausa fra la prima e la seconda scrittura; manda la richiesta, aspetta che la
transazione risulti aperta nel database, uccide il processo e confronta il database prima e dopo.

La pausa è inserita solo nel processo figlio avviato da questo script e non fa parte del codice
dell'applicazione.
"""

import asyncio
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from datetime import date
from decimal import Decimal
from typing import Any

import httpx
from sqlalchemy import text

from scripts import seed_accounts
from src.db.session import AsyncSessionLocal, engine

PORTA = 8001
PAUSA = 30  # secondi; il processo viene ucciso molto prima che scada
URL = f"http://127.0.0.1:{PORTA}"


def server() -> None:
    """Esegue l'applicazione vera, rallentata fra la prima e la seconda scrittura."""
    import uvicorn

    from src.db.models import ChatMessage
    from src.db.repos import AccountRepository, ChatRepository
    from src.main import app

    add_message = ChatRepository.add_message
    apply = AccountRepository.apply

    async def add_message_lento(
        self: ChatRepository,
        session_id: str,
        role: str,
        content: str,
        tokens: int = 0,
        cost_eur: Decimal = Decimal("0"),
        model_used: str | None = None,
    ) -> ChatMessage:
        if role == "assistant":  # il messaggio dell'utente è già scritto (flush), la risposta no
            await asyncio.sleep(PAUSA)
        return await add_message(self, session_id, role, content, tokens, cost_eur, model_used)

    async def apply_lento(
        self: AccountRepository, account_id: str, amount: Decimal
    ) -> Decimal | None:
        await asyncio.sleep(PAUSA)  # il movimento è già scritto (flush), il saldo no
        return await apply(self, account_id, amount)

    setattr(ChatRepository, "add_message", add_message_lento)  # noqa: B010
    setattr(AccountRepository, "apply", apply_lento)  # noqa: B010
    uvicorn.run(app, port=PORTA, log_level="warning")


async def _leggi(sql: str, **parametri: object) -> list[tuple[Any, ...]]:
    try:
        async with AsyncSessionLocal() as s:
            return [tuple(r) for r in (await s.execute(text(sql), parametri)).all()]
    finally:
        await engine.dispose()  # ogni asyncio.run ha il suo loop, quindi il pool non va riusato


def leggi(sql: str, **parametri: object) -> list[tuple[Any, ...]]:
    return asyncio.run(_leggi(sql, **parametri))


def fotografia() -> tuple[Any, ...]:
    return leggi(
        "SELECT (SELECT COUNT(*) FROM chat_sessions), (SELECT COUNT(*) FROM chat_messages),"
        " (SELECT COUNT(*) FROM movements), (SELECT balance FROM accounts WHERE id = :conto)",
        conto=seed_accounts.PRINCIPALE,
    )[0]


def transazioni_aperte() -> list[tuple[Any, ...]]:
    return leggi(
        "SELECT pid, left(query, 70) FROM pg_stat_activity"
        " WHERE datname = current_database() AND state = 'idle in transaction'"
    )


def aspetta(condizione: str, verifica: Callable[[], bool], secondi: float = 15) -> None:
    fine = time.monotonic() + secondi
    while time.monotonic() < fine:
        if verifica():
            return
        time.sleep(0.3)
    raise SystemExit(f"Prova non conclusa: {condizione} non si è verificato in {secondi} secondi")


def prova(nome: str, percorso: str, corpo: dict[str, str]) -> bool:
    print(f"\n== {nome}")
    figlio = subprocess.Popen([sys.executable, "-m", "scripts.prova_interruzione", "--server"])
    try:

        def risponde() -> bool:
            try:
                return httpx.get(f"{URL}/health", timeout=1).status_code == 200
            except httpx.HTTPError:
                return False

        aspetta("l'avvio del server", risponde)
        prima = fotografia()
        esito: list[str] = []

        def manda() -> None:
            try:
                r = httpx.post(f"{URL}{percorso}", json=corpo, timeout=PAUSA + 10)
                esito.append(f"risposta {r.status_code}")
            except httpx.HTTPError as e:
                esito.append(f"nessuna risposta ({type(e).__name__})")

        richiesta = threading.Thread(target=manda)
        richiesta.start()
        aspetta("la transazione aperta", lambda: bool(transazioni_aperte()))
        in_volo = transazioni_aperte()[0]
        print(f"  a metà: transazione aperta nel database, ultima istruzione: {in_volo[1]!r}")
        print(f"  a metà, visto da fuori: {fotografia()} (la prima scrittura non si vede)")
        figlio.kill()  # TerminateProcess su Windows, SIGKILL altrove, senza codice di chiusura
        figlio.wait()
        richiesta.join()
        print(f"  processo ucciso; il client: {esito[0]}")
        aspetta("la chiusura della transazione orfana", lambda: not transazioni_aperte())
        dopo = fotografia()
        print("  (sessioni, messaggi, movimenti, saldo del conto principale)")
        print(f"  prima: {prima}\n  dopo:  {dopo}")
        integro = prima == dopo
        verdetto = "niente a metà, il database è come prima" if integro else "MEZZA OPERAZIONE"
        print("  ESITO:", verdetto)
        return integro
    finally:
        if figlio.poll() is None:
            figlio.kill()


async def prepara() -> None:
    await seed_accounts.main()  # il conto di Paolo Ferri deve esistere
    await engine.dispose()  # nello stesso loop che ha aperto le connessioni


def main() -> None:
    asyncio.run(prepara())
    chat = prova(
        "chat: il messaggio dell'utente, poi la risposta",
        "/api/ai/chat",
        {"session_id": "new", "message": "Interrotto a metà"},
    )
    movimento = prova(
        "movimento: il movimento, poi il saldo",
        f"/api/ai/accounts/{seed_accounts.PRINCIPALE}/movements",
        {"booking_date": str(date.today()), "description": "Interrotto", "amount": "-25.00"},
    )
    sys.exit(0 if chat and movimento else 1)


if __name__ == "__main__":
    server() if "--server" in sys.argv else main()
