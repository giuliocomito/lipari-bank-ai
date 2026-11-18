"""Misura dell'estensione del Giorno 4: che cosa resta nel database se il client chiude a metà.

Un modello finto risponde in quattro pezzi; il «client» ne legge due e poi chiude, come chi
chiude la pagina. Lo script riporta che cosa è finito nella tabella dei messaggi: quante
risposte, con quale testo e con quale costo. Non chiama modelli veri e usa il database di test.

    uv run python -m scripts.misura_stream_interrotto
"""

import asyncio
import os
from collections.abc import AsyncGenerator
from decimal import Decimal

os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://lipari:lipari@localhost:5432/lipari_ai_test"
)
os.environ.setdefault("JWT_SECRET", "segreto-della-misura-lungo-almeno-trentadue-caratteri")

from sqlalchemy import select, text  # noqa: E402

from src.db.models import ChatMessage  # noqa: E402
from src.db.session import AsyncSessionLocal, engine  # noqa: E402
from src.llm.types import LLMResponse, Message, ToolSpec  # noqa: E402
from src.services.chat_service import ChatService  # noqa: E402
from src.types.chat import ChatRequest  # noqa: E402

PEZZI = ["Il saldo ", "del conto principale ", "di Paolo Ferri ", "è di 48.200,00 euro."]
COSTO_INTERO = Decimal("0.004")  # il costo che il finto dichiarerebbe a risposta completa


class ModelloAPezzi:
    """Risponde a pezzi con una breve pausa fra l'uno e l'altro, come un modello vero."""

    model = "claude-opus-5-5"

    async def complete(
        self, messages: list[Message], max_tokens: int = 500, tools: list[ToolSpec] | None = None
    ) -> LLMResponse:
        raise NotImplementedError

    async def stream(
        self, messages: list[Message], max_tokens: int = 500
    ) -> AsyncGenerator[str | LLMResponse, None]:
        for pezzo in PEZZI:
            await asyncio.sleep(0.01)
            yield pezzo
        yield LLMResponse(
            content="".join(PEZZI), tokens_used=300, cost_eur=COSTO_INTERO, model="claude-opus-5-5"
        )


async def main() -> None:
    async with engine.begin() as c:
        await c.execute(text("TRUNCATE chat_messages, chat_sessions CASCADE"))
    async with AsyncSessionLocal() as s:
        servizio = ChatService(s, ModelloAPezzi(), "Sei l'assistente.", Decimal("5"))
        domanda = ChatRequest(session_id="new", message="Quanto ha Paolo sul conto principale?")
        pezzi = await servizio.chat_stream(domanda, user_id="mbianchi")
        letti = [await anext(pezzi), await anext(pezzi)]  # il client legge due pezzi...
        await pezzi.aclose()  # ...e chiude la pagina
    async with AsyncSessionLocal() as s:
        risposte = (
            await s.scalars(select(ChatMessage).where(ChatMessage.role == "assistant"))
        ).all()
    await engine.dispose()
    print(f"pezzi ricevuti dal client: {len(letti)} su {len(PEZZI)} ({''.join(letti)!r})")
    print(f"risposte salvate: {len(risposte)}")
    for r in risposte:
        print(f"  testo salvato: {r.content!r}")
        print(f"  token: {r.tokens}, costo registrato: {r.cost_eur} EUR")
        print(f"  segnata come interrotta: {getattr(r, 'interrupted', 'colonna assente')}")
    if not risposte:
        print("  nessuna riga: il costo di questa risposta non entra nel tetto né nei report")


if __name__ == "__main__":
    asyncio.run(main())
