"""Stima del consumo di uno stream interrotto prima della fine.

Il conteggio esatto dei token arriva solo con l'ultimo evento dello stream, che manca se il
client chiude la pagina o il fornitore cade. La generazione avvenuta va comunque pagata, quindi
qui la si stima dai caratteri. Secondo il glossario di Anthropic, sui modelli precedenti un
token vale circa 3,5 caratteri di testo inglese e i modelli recenti producono circa il 30% di
token in più: 3,5 / 1,3 ≈ 2,7 caratteri per token. La stima non conta i token di
ragionamento, che lo stream non mostra, quindi per l'output è per difetto.
"""

import math
from decimal import Decimal

from src.llm.anthropic_provider import PRICING as PREZZI_ANTHROPIC
from src.llm.openai_provider import PRICING as PREZZI_OPENAI
from src.llm.types import LLMResponse, Message

CARATTERI_PER_TOKEN = 2.7
LISTINO: dict[str, tuple[Decimal, Decimal]] = {**PREZZI_ANTHROPIC, **PREZZI_OPENAI}


def token_stimati(testo: str) -> int:
    return math.ceil(len(testo) / CARATTERI_PER_TOKEN)


def stima_interrotta(modello: str, messaggi: list[Message], testo_parziale: str) -> LLMResponse:
    """Stima il consumo di una risposta interrotta: tutto l'input e l'output ricevuto fin lì."""
    entrata = sum(token_stimati(m.content) for m in messaggi)
    uscita = token_stimati(testo_parziale)
    prezzo_in, prezzo_out = LISTINO.get(modello, (Decimal("0"), Decimal("0")))
    return LLMResponse(
        content=testo_parziale,
        tokens_used=entrata + uscita,
        cost_eur=(entrata * prezzo_in + uscita * prezzo_out) / 1000,
        model=modello,
    )
