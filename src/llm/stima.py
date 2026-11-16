# src/llm/stima.py — il costo di una risposta interrotta, quando il fornitore non l'ha detto
"""La stima del consumo di uno stream che non è arrivato alla fine.

Il conteggio esatto dei token arriva solo con l'ultimo evento dello stream: se il client chiude
la pagina, o il fornitore cade, quell'evento non arriva mai. La generazione però c'è stata, e
si paga. Qui si stima dai caratteri: il glossario di Anthropic dice che sui modelli precedenti
un token vale circa 3,5 caratteri di testo inglese e che i modelli recenti producono circa il
30% di token in più, quindi 3,5 / 1,3 ≈ 2,7 caratteri per token. È una stima, e lo resta: non
conta i token di ragionamento, che lo stream non mostra, quindi sull'output è per difetto.
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
    """Il consumo stimato di una risposta fermata a metà: tutto l'input, l'output arrivato."""
    entrata = sum(token_stimati(m.content) for m in messaggi)
    uscita = token_stimati(testo_parziale)
    prezzo_in, prezzo_out = LISTINO.get(modello, (Decimal("0"), Decimal("0")))
    return LLMResponse(
        content=testo_parziale,
        tokens_used=entrata + uscita,
        cost_eur=(entrata * prezzo_in + uscita * prezzo_out) / 1000,
        model=modello,
    )
