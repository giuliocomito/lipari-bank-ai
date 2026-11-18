import re

from src.llm.client import LLMProvider
from src.llm.embedding_client import EmbeddingClient
from src.llm.types import Message
from src.services.retrieval_service import RetrievalResult, RetrievalService
from src.types.advice import AdviceRequest, AdviceResponse, Citation

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


class RAGService:
    """Risponde a partire dai passaggi recuperati e cita le fonti effettivamente usate."""

    def __init__(
        self,
        retrieval: RetrievalService,
        embedder: EmbeddingClient,
        llm: LLMProvider,
        prompt: str,
        max_tokens: int = 1000,
    ) -> None:
        self.retrieval = retrieval
        self.embedder = embedder
        self.llm = llm
        self.prompt = prompt
        self.max_tokens = max_tokens  # con Claude include anche il ragionamento

    async def advise(self, req: AdviceRequest) -> AdviceResponse:
        """Risponde alla domanda con le fonti usate.

        Se nessun passaggio supera la soglia restituisce il rifiuto, senza citazioni e senza
        chiamare il modello.
        """
        vettore = await self.embedder.embed_one(req.question)
        passaggi = await self.retrieval.search(vettore)
        if not passaggi:
            return AdviceResponse(answer=RIFIUTO, citations=[], tokens_used=0, cost_eur=0.0)

        risposta = await self.llm.complete(
            [
                Message(role="system", content=self.prompt),
                Message(
                    role="user",
                    content=f"CONTESTO\n{contesto(passaggi)}\n\nDOMANDA\n{req.question}",
                ),
            ],
            self.max_tokens,
        )
        rifiuto = RIFIUTO in risposta.content  # se il modello rifiuta, le fonti non si citano
        return AdviceResponse(
            answer=risposta.content,
            citations=[] if rifiuto else citazioni(risposta.content, passaggi),
            tokens_used=risposta.tokens_used,
            cost_eur=float(risposta.cost_eur),
        )
