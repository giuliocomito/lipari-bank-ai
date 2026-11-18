# Modelli finti per i test. Le risposte sono simulate a livello HTTP, così gli SDK veri fanno
# il loro lavoro; ModelloEco invece ripete la domanda.
import hashlib
import json
import math
import re
from collections.abc import AsyncGenerator, Callable
from decimal import Decimal
from typing import Any

import httpx2
from anthropic import AsyncAnthropic
from openai import AsyncOpenAI

from src.db.models import DIMENSIONI_EMBEDDING
from src.llm.embedding_client import EmbeddingClient
from src.llm.types import LLMResponse, Message, ToolSpec
from src.services.categorize_rules import categorizza
from src.types.categorize import CategorizeRequest, CategorizeResponse

Gestore = Callable[[httpx2.Request], httpx2.Response]
CLAUDE = "claude-opus-5-5"


class Registro:
    """Registra corpo JSON e percorso di ogni richiesta ricevuta dal finto."""

    def __init__(self) -> None:
        self.richieste: list[dict[str, Any]] = []
        self.percorsi: list[str] = []

    def annota(self, request: httpx2.Request) -> dict[str, Any]:
        corpo: dict[str, Any] = json.loads(request.content or b"{}")
        self.richieste.append(corpo)
        self.percorsi.append(request.url.path)
        return corpo


def openai_finto(gestore: Gestore, max_retries: int = 2) -> AsyncOpenAI:
    return AsyncOpenAI(
        api_key="sk-test",
        base_url="http://finto/v1",
        max_retries=max_retries,
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(gestore)),
    )


def anthropic_finto(gestore: Gestore, max_retries: int = 2) -> AsyncAnthropic:
    return AsyncAnthropic(
        api_key="sk-ant-test",
        base_url="http://finto",
        max_retries=max_retries,
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(gestore)),
    )


# Risposte di OpenAI
def completion(
    testo: str | None,
    *,
    prompt: int = 100,
    uscita: int = 20,
    tool_calls: list[dict[str, Any]] | None = None,
) -> httpx2.Response:
    messaggio: dict[str, Any] = {"role": "assistant", "content": testo}
    if tool_calls:
        messaggio["tool_calls"] = tool_calls
    return httpx2.Response(
        200,
        json={
            "id": "c1",
            "object": "chat.completion",
            "created": 0,
            "model": "gpt-4o-mini",
            "choices": [
                {
                    "index": 0,
                    "message": messaggio,
                    "finish_reason": "tool_calls" if tool_calls else "stop",
                }
            ],
            "usage": {
                "prompt_tokens": prompt,
                "completion_tokens": uscita,
                "total_tokens": prompt + uscita,
            },
        },
    )


def chiamata(id_: str, nome: str, argomenti: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": id_,
        "type": "function",
        "function": {"name": nome, "arguments": json.dumps(argomenti)},
    }


def stream_openai(pezzi: list[str], *, prompt: int = 80, uscita: int = 12) -> httpx2.Response:
    righe: list[dict[str, Any]] = [
        {
            "id": "c1",
            "object": "chat.completion.chunk",
            "created": 0,
            "model": "gpt-4o-mini",
            "choices": [{"index": 0, "delta": {"content": p}, "finish_reason": None}],
        }
        for p in pezzi
    ]
    righe.append(
        {
            "id": "c1",
            "object": "chat.completion.chunk",
            "created": 0,
            "model": "gpt-4o-mini",
            "choices": [],  # l'ultimo chunk porta solo il consumo
            "usage": {
                "prompt_tokens": prompt,
                "completion_tokens": uscita,
                "total_tokens": prompt + uscita,
            },
        }
    )
    corpo = "".join(f"data: {json.dumps(r)}\n\n" for r in righe) + "data: [DONE]\n\n"
    return httpx2.Response(200, text=corpo, headers={"content-type": "text/event-stream"})


# Risposte di Anthropic
def messaggio_anthropic(
    testo: str,
    *,
    entrata: int = 50,
    uscita: int = 10,
    strumenti: list[tuple[str, str, dict[str, Any]]] | None = None,
    pensiero: str | None = None,
    stop: str | None = None,
) -> httpx2.Response:
    """Risposta di Claude con pensiero, testo e blocchi tool_use (id, nome, argomenti)."""
    blocchi: list[dict[str, Any]] = []
    if pensiero is not None:  # il ragionamento si paga ma non va mostrato
        blocchi.append({"type": "thinking", "thinking": pensiero, "signature": "firma"})
    if testo:
        blocchi.append({"type": "text", "text": testo})
    blocchi += [{"type": "tool_use", "id": i, "name": n, "input": a} for i, n, a in strumenti or []]
    return httpx2.Response(
        200,
        json={
            "id": "m1",
            "type": "message",
            "role": "assistant",
            "model": CLAUDE,
            "content": blocchi,
            "stop_reason": stop or ("tool_use" if strumenti else "end_turn"),
            "stop_sequence": None,
            "usage": {"input_tokens": entrata, "output_tokens": uscita},
        },
    )


def stream_anthropic(pezzi: list[str], *, entrata: int = 50, uscita: int = 10) -> httpx2.Response:
    eventi: list[tuple[str, dict[str, Any]]] = [
        (
            "message_start",
            {
                "type": "message_start",
                "message": {
                    "id": "m1",
                    "type": "message",
                    "role": "assistant",
                    "model": CLAUDE,
                    "content": [],
                    "stop_reason": None,
                    "stop_sequence": None,
                    "usage": {"input_tokens": entrata, "output_tokens": 1},
                },
            },
        ),
        (
            "content_block_start",
            {
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "text", "text": ""},
            },
        ),
    ]
    for p in pezzi:
        eventi.append(
            (
                "content_block_delta",
                {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "text_delta", "text": p},
                },
            )
        )
    eventi += [
        ("content_block_stop", {"type": "content_block_stop", "index": 0}),
        (
            "message_delta",
            {
                "type": "message_delta",
                "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                "usage": {"output_tokens": uscita},
            },
        ),
        ("message_stop", {"type": "message_stop"}),
    ]
    corpo = "".join(f"event: {e}\ndata: {json.dumps(d)}\n\n" for e, d in eventi)
    return httpx2.Response(200, text=corpo, headers={"content-type": "text/event-stream"})


# Finti che il conftest installa per tutta la sessione
class ModelloEco:
    """Ripete la domanda a costo zero, per i test che non chiedono una risposta precisa."""

    model = "eco"

    async def complete(
        self, messages: list[Message], max_tokens: int = 500, tools: list[ToolSpec] | None = None
    ) -> LLMResponse:
        return LLMResponse(
            content=f"Echo: {messages[-1].content}",
            tokens_used=0,
            cost_eur=Decimal("0"),
            model="eco",
        )

    async def stream(
        self, messages: list[Message], max_tokens: int = 500
    ) -> AsyncGenerator[str | LLMResponse, None]:
        risposta = await self.complete(messages, max_tokens)
        yield risposta.content
        yield risposta


class CategorizzazioneARegole:
    """Categorizza con la regola a parole chiave, gratuita e deterministica."""

    async def categorize(self, req: CategorizeRequest) -> CategorizeResponse:
        return categorizza(req)


# Embedding finti, dal Giorno 5
def vettore(testo: str) -> list[float]:
    """Embedding finto ma coerente, in cui le parole in comune avvicinano i testi.

    Ogni parola di almeno tre lettere incrementa una posizione del vettore scelta con un hash,
    poi il vettore viene normalizzato. Testi con parole in comune hanno similarità del coseno
    alta, testi senza parole in comune similarità zero; così la soglia e l'ordine del recupero
    si verificano davvero, su Postgres con pgvector e l'indice HNSW.
    """
    v = [0.0] * DIMENSIONI_EMBEDDING
    for parola in re.findall(r"\w{3,}", testo.lower()):
        v[int(hashlib.md5(parola.encode()).hexdigest(), 16) % DIMENSIONI_EMBEDDING] += 1.0
    norma = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / norma for x in v]


def gestore_embedding(r: httpx2.Request) -> httpx2.Response:
    """Simula l'API degli embedding: un vettore per ogni testo, nell'ordine di arrivo."""
    testi: list[str] = json.loads(r.content)["input"]
    return httpx2.Response(
        200,
        json={
            "object": "list",
            "model": "bge-m3",
            "data": [
                {"object": "embedding", "index": i, "embedding": vettore(t)}
                for i, t in enumerate(testi)
            ],
            "usage": {"prompt_tokens": 10, "total_tokens": 10},
        },
    )


def embedder_finto() -> EmbeddingClient:
    return EmbeddingClient(openai_finto(gestore_embedding), "bge-m3")


class ModelloFisso:
    """Risponde con il testo scelto dal test e registra i messaggi ricevuti."""

    model = "finto"

    def __init__(self, risposta: str) -> None:
        self.risposta = risposta
        self.ricevuti: list[list[Message]] = []

    async def complete(
        self, messages: list[Message], max_tokens: int = 500, tools: list[ToolSpec] | None = None
    ) -> LLMResponse:
        self.ricevuti.append(messages)
        return LLMResponse(
            content=self.risposta, tokens_used=100, cost_eur=Decimal("0.0001"), model="finto"
        )

    async def stream(
        self, messages: list[Message], max_tokens: int = 500
    ) -> AsyncGenerator[str | LLMResponse, None]:
        yield await self.complete(messages, max_tokens)
