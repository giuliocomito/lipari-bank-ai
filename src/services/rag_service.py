import asyncio
import logging
import re
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from decimal import Decimal

from src.auth.deps import UserContext
from src.exceptions import LLMProviderError
from src.llm.client import LLMProvider
from src.llm.embedding_client import EmbeddingClient
from src.llm.rewriter import QueryRewriter
from src.llm.types import Message
from src.services.retrieval_service import RetrievalResult, RetrievalService
from src.types.advice import AdviceResponse, Citation

logger = logging.getLogger(__name__)

RIFIUTO = "Non ho trovato informazioni sufficienti nei documenti disponibili."
MARCATORE = re.compile(r"\[fonte-(\d+)\]")


def contesto(passaggi: list[RetrievalResult]) -> str:
    """Etichetta i passaggi con [fonte-N], così il modello può citarli."""
    return "\n\n".join(
        f"[fonte-{i}] (documento: {p.document_id})\n{p.content}"
        for i, p in enumerate(passaggi, start=1)
    )


def citazioni(risposta: str, passaggi: list[RetrievalResult]) -> list[Citation]:
    """Le fonti citate nella risposta, senza duplicati e nell'ordine in cui compaiono."""
    usati: list[Citation] = []
    visti: set[tuple[str, str]] = set()
    for numero in MARCATORE.findall(risposta):
        indice = int(numero) - 1
        if not 0 <= indice < len(passaggi):
            continue  # marcatore senza passaggio corrispondente, inventato dal modello
        p = passaggi[indice]
        if (p.document_id, p.content) in visti:
            continue
        visti.add((p.document_id, p.content))
        usati.append(
            Citation(
                document_id=p.document_id,
                chunk_id=p.chunk_id,
                excerpt=p.content[:200],
                similarity=p.similarity,
            )
        )
    return usati


@dataclass
class Fasi:
    """Millisecondi spesi in ogni fase, per il log della richiesta."""

    rewrite_ms: int = 0
    embedding_ms: int = 0
    retrieval_ms: int = 0
    prompt_ms: int = 0
    llm_ms: int = 0
    used_fallback: bool = False

    @property
    def total_ms(self) -> int:
        return (
            self.rewrite_ms + self.embedding_ms + self.retrieval_ms + self.prompt_ms + self.llm_ms
        )


@dataclass
class Generazione:
    """Il risultato della generazione. Se il modello non viene chiamato, il costo è zero."""

    testo: str
    tokens_used: int = 0
    cost_eur: Decimal = Decimal("0")
    degradata: bool = False


@contextmanager
def _cronometro(fasi: Fasi, campo: str) -> Iterator[None]:
    inizio = time.perf_counter()
    try:
        yield
    finally:
        setattr(fasi, campo, int((time.perf_counter() - inizio) * 1000))


class RAGService:
    """Riscrive la domanda, recupera i passaggi visibili al ruolo, genera e misura ogni fase."""

    TIMEOUT_GENERAZIONE_S = 10

    def __init__(
        self,
        retrieval: RetrievalService,
        embedder: EmbeddingClient,
        llm: LLMProvider,
        rewriter: QueryRewriter,
        prompt: str,
        max_tokens: int = 1000,
    ) -> None:
        self.retrieval = retrieval
        self.embedder = embedder
        self.llm = llm
        self.rewriter = rewriter
        self.prompt = prompt
        self.max_tokens = max_tokens  # con Claude include anche il ragionamento

    async def advise(self, question: str, user: UserContext) -> AdviceResponse:
        """Risponde alla domanda con le fonti usate, cercando solo fra i documenti del ruolo.

        Se nessun passaggio supera la soglia restituisce il rifiuto, senza citazioni e senza
        chiamare il modello.
        """
        fasi = Fasi()

        with _cronometro(fasi, "rewrite_ms"):
            search_query = await self.rewriter.rewrite_cached(question)

        with _cronometro(fasi, "embedding_ms"):
            query_vec = await self.embedder.embed_one(search_query)

        with _cronometro(fasi, "retrieval_ms"):
            chunks = await self.retrieval.search_for_user(query_vec, user.role, user.username)

        if chunks:
            with _cronometro(fasi, "prompt_ms"):
                # La riscritta serve al recupero; al modello va la domanda dell'utente.
                messaggi = [
                    Message(role="system", content=self.prompt),
                    Message(
                        role="user",
                        content=f"CONTESTO\n{contesto(chunks)}\n\nDOMANDA\n{question}",
                    ),
                ]
            with _cronometro(fasi, "llm_ms"):
                gen = await self._generate_or_degrade(messaggi, chunks)
        else:
            gen = Generazione(RIFIUTO)
        fasi.used_fallback = gen.degradata

        logger.info(
            "advice_completata",
            extra={
                "username": user.username,
                "role": user.role,
                "chunk_count": len(chunks),
                "chunk_ids": [r.chunk_id for r in chunks],  # gli id, mai il testo
                **asdict(fasi),
                "total_ms": fasi.total_ms,
            },
        )
        rifiuto = RIFIUTO in gen.testo  # se il modello rifiuta, le fonti non si citano
        return AdviceResponse(
            answer=gen.testo,
            citations=[] if rifiuto else citazioni(gen.testo, chunks),
            tokens_used=gen.tokens_used,
            cost_eur=float(gen.cost_eur),
            rewritten_query=search_query,
        )

    async def _generate_or_degrade(
        self, messaggi: list[Message], chunks: list[RetrievalResult]
    ) -> Generazione:
        """Chiama il modello; se cade o supera il timeout, restituisce i passaggi con le fonti."""
        try:
            async with asyncio.timeout(self.TIMEOUT_GENERAZIONE_S):
                risposta = await self.llm.complete(messaggi, self.max_tokens)
            return Generazione(risposta.content, risposta.tokens_used, risposta.cost_eur)
        except (LLMProviderError, TimeoutError):
            logger.warning("generator_non_disponibile_fallback_su_chunk")
            estratti = "\n\n".join(
                f"[fonte-{i}] {r.document_id}\n{r.content}"
                for i, r in enumerate(chunks[:3], start=1)
            )
            return Generazione(
                "⚠️ Risposta parziale: il servizio di sintesi non è momentaneamente "
                "disponibile. Di seguito i passaggi dei documenti più pertinenti "
                f"alla tua domanda.\n\n{estratti}",
                degradata=True,
            )
