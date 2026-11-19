# Riscrittura della domanda dell'utente in una forma che il recupero sa cercare.
import hashlib
import logging

from src.llm.client import LLMProvider
from src.llm.types import Message

log = logging.getLogger(__name__)


class QueryRewriter:
    """Riscrive la domanda per il recupero; se non ci riesce, il recupero usa l'originale."""

    def __init__(self, llm: LLMProvider, prompt: str, enabled: bool = True) -> None:
        self.llm = llm
        self.prompt = prompt
        self.enabled = enabled  # spento, il recupero cerca sulla domanda originale
        self._cache: dict[str, str] = {}  # vive nel processo: con più processi non è condivisa

    async def _riscrivi(self, question: str, history: list[str] | None) -> str | None:
        """La riscrittura, oppure None se il modello non risponde o risponde male."""
        coda = "\n".join(history[-3:]) if history else ""
        try:
            risposta = await self.llm.complete(
                [
                    Message(role="system", content=self.prompt),
                    Message(role="user", content=f"{coda}\n\nDomanda: {question}".strip()),
                ],
                max_tokens=80,
            )
        except Exception:
            log.warning("rewriter.fallito", extra={"domanda": question})
            return None

        riscritta = risposta.content.strip().strip('"')
        # Un'uscita vuota, o molto più lunga della domanda, è probabilmente una risposta
        # invece di una riscrittura: si scarta e si cerca sull'originale.
        if not riscritta or len(riscritta) > 4 * len(question) + 80:
            log.warning("rewriter.scartata", extra={"uscita": riscritta[:120]})
            return None
        return riscritta

    async def rewrite(self, question: str, history: list[str] | None = None) -> str:
        """Riscrive la domanda; se la riscrittura fallisce restituisce l'originale."""
        if not self.enabled:
            return question
        return await self._riscrivi(question, history) or question

    async def rewrite_cached(self, question: str) -> str:
        """Come rewrite, ma la stessa domanda si riscrive una volta sola.

        Il ripiego sull'originale non entra in cache, così alla volta successiva si riprova.
        """
        if not self.enabled:
            return question
        key = f"rewrite:{hashlib.sha256(question.encode()).hexdigest()}"
        if (cached := self._cache.get(key)) is not None:
            return cached
        riscritta = await self._riscrivi(question, None)
        if riscritta is None:
            return question
        self._cache[key] = riscritta
        return riscritta
