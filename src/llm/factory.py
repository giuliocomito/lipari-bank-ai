# Scelta del fornitore di modelli e creazione dei client, in un unico punto.
from dataclasses import dataclass, field
from functools import cache
from typing import Any

import instructor
from anthropic import AsyncAnthropic
from openai import AsyncOpenAI

from src.config import settings
from src.exceptions import AppError
from src.llm.anthropic_provider import AnthropicProvider
from src.llm.client import LLMProvider
from src.llm.embedding_client import EmbeddingClient
from src.llm.openai_provider import OpenAIProvider


def _chiave(valore: str, nome: str) -> str:
    if not valore:  # l'SDK fallirebbe comunque, ma senza dire quale chiave manca
        raise AppError(503, "LLM_NOT_CONFIGURED", f"Manca {nome}: il modello non è configurato")
    return valore


@cache  # un client per processo, così il pool di connessioni si riusa
def _openai() -> AsyncOpenAI:
    # timeout esplicito perché il default dell'SDK è di dieci minuti; max_retries è il default
    return AsyncOpenAI(
        api_key=_chiave(settings.openai_api_key, "OPENAI_API_KEY"), timeout=20.0, max_retries=2
    )


@cache
def _anthropic() -> AsyncAnthropic:
    return AsyncAnthropic(
        api_key=_chiave(settings.anthropic_api_key, "ANTHROPIC_API_KEY"),
        timeout=30.0,  # più largo che nel corso, perché Claude ragiona prima di rispondere
        max_retries=2,
    )


def get_llm_provider() -> LLMProvider:
    modello = settings.default_model
    if modello.startswith("claude"):
        return AnthropicProvider(_anthropic(), modello, settings.llm_effort)
    if modello.startswith("gpt"):
        return OpenAIProvider(_openai(), modello)
    raise ValueError(f"Modello sconosciuto: {modello}")


@cache
def _embedding() -> AsyncOpenAI:
    """Client OpenAI per gli embedding, puntato su Ollama tramite EMBEDDING_BASE_URL.

    Ollama non usa chiavi, ma l'SDK ne pretende una non vuota: qualsiasi stringa va bene.
    """
    return AsyncOpenAI(
        base_url=settings.embedding_base_url, api_key="ollama", timeout=30.0, max_retries=2
    )


def get_embedder() -> EmbeddingClient:
    # documenti e domande vanno vettorizzati con lo stesso modello: vettori di modelli diversi
    # stanno in spazi diversi e non sono confrontabili
    return EmbeddingClient(_embedding(), settings.embedding_model)


@dataclass(frozen=True)
class Strutturato:
    """Client Instructor con il modello e i parametri adatti al fornitore scelto.

    Le differenze fra i due SDK restano qui, così il servizio che chiede output strutturato non
    le vede. Con Claude si omette temperature (i modelli attuali rispondono 400) e si usa
    tool_choice "auto", perché Opus 5.5 rifiuta lo strumento forzato, default di Instructor.
    """

    client: instructor.AsyncInstructor
    model: str
    fornitore: str
    opzioni: dict[str, Any] = field(default_factory=dict)


OPZIONI_STRUTTURATE: dict[str, dict[str, Any]] = {
    "anthropic": {
        "tool_choice": {"type": "auto"},
        "output_config": {"effort": "low"},  # per classificare basta poco ragionamento
    },
    "openai": {"temperature": 0.0},  # minima variabilità, che non equivale a determinismo
}


@cache
def get_strutturato() -> Strutturato:
    modello = settings.default_model
    if modello.startswith("claude"):
        return Strutturato(
            client=instructor.from_anthropic(_anthropic()),
            model=modello,
            fornitore="anthropic",
            opzioni=OPZIONI_STRUTTURATE["anthropic"],
        )
    if modello.startswith("gpt"):
        return Strutturato(
            client=instructor.from_openai(_openai()),
            model=modello,
            fornitore="openai",
            opzioni=OPZIONI_STRUTTURATE["openai"],
        )
    raise ValueError(f"Modello sconosciuto: {modello}")
