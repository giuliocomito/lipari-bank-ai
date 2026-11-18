"""Esegue con un solo comando le cinque prove di «Come si vede che è fatta» del Project Work G4.

Ogni prova manda una richiesta HTTP all'applicazione FastAPI, che passa per gli endpoint, i
servizi, la factory, i provider e gli SDK veri di Anthropic e di OpenAI. Solo il server del
fornitore è finto e risponde con messaggi preparati, quindi le prove non richiedono una chiave
API, non costano nulla e danno sempre lo stesso risultato. Il database è quello di test,
svuotato e ripopolato con il seed.

    uv run python -m scripts.prove_g4
"""

import asyncio
import json
import logging
import os
from decimal import Decimal

os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://lipari:lipari@localhost:5432/lipari_ai_test"
)
os.environ.setdefault("JWT_SECRET", "segreto-delle-prove-lungo-almeno-trentadue-caratteri")

import httpx2  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import select, text  # noqa: E402

from scripts import seed_accounts  # noqa: E402
from scripts.misura_stream_interrotto import PEZZI, ModelloAPezzi  # noqa: E402
from src.config import settings  # noqa: E402
from src.db.models import ChatMessage  # noqa: E402
from src.db.session import AsyncSessionLocal, engine  # noqa: E402
from src.llm import factory  # noqa: E402
from src.main import app  # noqa: E402
from src.services.chat_service import ChatService  # noqa: E402
from src.types.chat import ChatRequest  # noqa: E402
from tests.finti import (  # noqa: E402
    Registro,
    anthropic_finto,
    completion,
    messaggio_anthropic,
    openai_finto,
)

CLAUDE, GPT = "claude-opus-5-5", "gpt-4o-mini"
ANNA = seed_accounts.ANNA
RISULTATI: list[tuple[str, bool, str]] = []


class Raccolta(logging.Handler):
    """Conserva i record di log con i campi extra, per mostrarli alla fine della prova."""

    def __init__(self) -> None:
        super().__init__()
        self.record: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.record.append(record)


def punta_su(nome: str, client: object) -> None:
    """Sostituisce un client della factory (_anthropic o _openai) con uno sul server finto."""
    setattr(factory, nome, lambda: client)


def esito(nome: str, ok: bool, dettaglio: str) -> None:
    RISULTATI.append((nome, ok, dettaglio))
    print(f"\n[{'OK' if ok else 'NO'}] {nome}\n     {dettaglio}")


def usa_fornitori_finti(gestore_claude: Registro, gestore_gpt: Registro) -> None:
    """Usa la factory vera con i client degli SDK puntati sui server finti."""

    def risponde_claude(r: httpx2.Request) -> httpx2.Response:
        gestore_claude.annota(r)
        return messaggio_anthropic(
            "Servono un documento d'identità e il codice fiscale.", entrata=1500, uscita=300
        )

    def risponde_gpt(r: httpx2.Request) -> httpx2.Response:
        gestore_gpt.annota(r)
        return completion(
            "Servono un documento d'identità e il codice fiscale.", prompt=1500, uscita=300
        )

    client_claude, client_gpt = anthropic_finto(risponde_claude), openai_finto(risponde_gpt)
    punta_su("_anthropic", client_claude)
    punta_su("_openai", client_gpt)
    factory.get_strutturato.cache_clear()


async def prova_contratto(c: AsyncClient) -> None:
    """Ripete la stessa domanda cambiando solo DEFAULT_MODEL, senza toccare il codice."""
    reg_claude, reg_gpt = Registro(), Registro()
    usa_fornitori_finti(reg_claude, reg_gpt)
    righe = []
    for modello in (CLAUDE, GPT):
        settings.default_model = modello
        r = await c.post(
            "/api/ai/chat", json={"session_id": "new", "message": "Cosa serve per aprire un conto?"}
        )
        d = r.json()
        righe.append(f"{d['model_used']}: {d['tokens_used']} token, {d['cost_eur']:.6f} EUR")
    ok = reg_claude.percorsi == ["/v1/messages"] and reg_gpt.percorsi == ["/v1/chat/completions"]
    esito(
        "1. Cambio di fornitore da una variabile (DEFAULT_MODEL)",
        ok,
        " | ".join(righe) + " — servizio, endpoint e tipi invariati",
    )
    settings.default_model = CLAUDE


async def prova_conto_di_anna(c: AsyncClient) -> None:
    """Il modello chiede il saldo di un conto di un altro portafoglio e lo strumento lo rifiuta."""
    raccolta = Raccolta()
    logging.getLogger("src.llm.tools").addHandler(raccolta)

    def risponde(r: httpx2.Request) -> httpx2.Response:
        corpo = json.loads(r.content)
        risultati = [
            b
            for m in corpo["messages"]
            if isinstance(m["content"], list)
            for b in m["content"]
            if b.get("type") == "tool_result"
        ]
        if not risultati:  # il modello asseconda l'utente e chiede quel saldo
            return messaggio_anthropic(
                "", strumenti=[("t1", "get_account_balance", {"account_id": ANNA})]
            )
        return messaggio_anthropic(f"Ho ricevuto: {risultati[0]['content']}")

    cliente = anthropic_finto(risponde)
    punta_su("_anthropic", cliente)
    domanda = f"Quanto c'è sul conto {ANNA} di Anna Greco?"
    r = await c.post("/api/ai/chat", json={"session_id": "new", "message": domanda})
    negati = [x for x in raccolta.record if x.getMessage() == "strumento_negato"]
    esito_strumento = r.json()["tool_calls"][0]["result"]
    ok = bool(negati) and "15300" not in r.text and esito_strumento.startswith("ERRORE")
    log = (
        f"operatore={negati[0].__dict__['operatore']} conto={negati[0].__dict__['conto']}"
        if negati
        else "nessun log"
    )
    esito(
        "2. Conto di un altro portafoglio (Anna Greco)",
        ok,
        f"lo strumento risponde «{esito_strumento}»; log strumento_negato: {log}; "
        "il saldo 15300 non compare",
    )


async def prova_tetto_a_zero(c: AsyncClient) -> None:
    reg = Registro()
    usa_fornitori_finti(reg, Registro())
    settings.daily_budget_eur = Decimal("0")
    r = await c.post("/api/ai/chat", json={"session_id": "new", "message": "Ciao"})
    settings.daily_budget_eur = Decimal("5.00")
    ok = r.status_code == 429 and not reg.richieste
    esito(
        "3. Tetto di spesa a zero",
        ok,
        f"HTTP {r.status_code} {r.json()['error']}, Retry-After {r.headers.get('Retry-After')} s, "
        f"chiamate al modello: {len(reg.richieste)}",
    )


async def prova_fuori_schema(c: AsyncClient) -> None:
    """Categorizza un movimento incomprensibile con un modello che inventa la categoria."""
    reg = Registro()

    def risponde(r: httpx2.Request) -> httpx2.Response:
        reg.annota(r)
        inventata = {"category": "BOH", "subcategory": "?", "confidence": 0.1, "reasoning": "?"}
        return messaggio_anthropic("", strumenti=[("c1", "CategorizeResponse", inventata)])

    cliente = anthropic_finto(risponde)
    punta_su("_anthropic", cliente)
    factory.get_strutturato.cache_clear()
    r = await c.post("/api/ai/categorize", json={"description": "xq#9 ?? zz 0040", "amount": 12.5})
    ok = r.status_code == 502 and len(reg.richieste) == 3
    esito(
        "4. Risposta fuori schema (categoria inventata)",
        ok,
        f"HTTP {r.status_code} {r.json()['error']} dopo {len(reg.richieste)} chiamate "
        "(1 + 2 ritentativi di Instructor, tutte pagate); niente salvato",
    )


async def prova_stream_interrotto() -> None:
    async with AsyncSessionLocal() as s:
        servizio = ChatService(s, ModelloAPezzi(), "Sei l'assistente.", Decimal("5"))
        pezzi = await servizio.chat_stream(
            ChatRequest(session_id="new", message="Quanto ha Paolo?"), user_id="mbianchi"
        )
        letti = [await anext(pezzi), await anext(pezzi)]
        await pezzi.aclose()
    async with AsyncSessionLocal() as s:
        salvata = (
            await s.scalars(
                select(ChatMessage)
                .where(ChatMessage.role == "assistant")
                .order_by(ChatMessage.seq.desc())
            )
        ).first()
    ok = salvata is not None and salvata.interrupted and salvata.content == "".join(letti)
    esito(
        "5. Stream interrotto a metà",
        ok,
        f"{len(letti)} pezzi su {len(PEZZI)} arrivati; nel database: {salvata.content!r}, "
        f"interrotta={salvata.interrupted}, {salvata.cost_eur} EUR stimati"
        if salvata
        else "nessuna riga",
    )


async def main() -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text("TRUNCATE chat_messages, chat_sessions, movements, accounts, customers CASCADE")
        )
    await seed_accounts.main()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://prove") as c:
        await prova_contratto(c)
        await prova_conto_di_anna(c)
        await prova_tetto_a_zero(c)
        await prova_fuori_schema(c)
    await prova_stream_interrotto()
    await engine.dispose()
    superate = sum(ok for _, ok, _ in RISULTATI)
    print(f"\nProve superate: {superate} su {len(RISULTATI)}")
    if superate != len(RISULTATI):
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
