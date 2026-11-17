# src/llm/factory.py — un solo posto decide quale fornitore, e con quali client
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
    if not valore:  # l'SDK rifiuta una chiave vuota: meglio un errore che dica quale manca
        raise AppError(503, "LLM_NOT_CONFIGURED", f"Manca {nome}: il modello non è configurato")
    return valore


@cache  # un client per processo: tiene il suo pool di connessioni
def _openai() -> AsyncOpenAI:
    # timeout scelto, non ereditato (il default è di dieci minuti); max_retries è quello dell'SDK
    return AsyncOpenAI(
        api_key=_chiave(settings.openai_api_key, "OPENAI_API_KEY"), timeout=20.0, max_retries=2
    )


@cache
def _anthropic() -> AsyncAnthropic:
    return AsyncAnthropic(
        api_key=_chiave(settings.anthropic_api_key, "ANTHROPIC_API_KEY"),
        timeout=30.0,  # Claude ragiona prima di rispondere: un margine in più del corso
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
    """Il client degli embedding: l'SDK di OpenAI, puntato su Ollama (EMBEDDING_BASE_URL).

    Ollama non chiede una chiave, ma l'SDK ne vuole una non vuota: qualsiasi stringa va bene.
    """
    return AsyncOpenAI(
        base_url=settings.embedding_base_url, api_key="ollama", timeout=30.0, max_retries=2
    )


def get_embedder() -> EmbeddingClient:
    # lo stesso modello per i documenti e per le domande: è la regola che non si viola, perché
    # vettori di modelli diversi vivono in spazi diversi e non si possono confrontare
    return EmbeddingClient(_embedding(), settings.embedding_model)


@dataclass(frozen=True)
class Strutturato:
    """Il client di Instructor, con il modello e i parametri che QUEL fornitore vuole o rifiuta.

    Le differenze fra i due SDK restano qui, e il servizio che chiede l'output strutturato
    non le vede: con Claude niente temperature (i modelli attuali la rifiutano con un 400) e
    tool_choice "auto" (Opus 5.5 rifiuta lo strumento forzato, che è il default di Instructor).
    """

    client: instructor.AsyncInstructor
    model: str
    fornitore: str
    opzioni: dict[str, Any] = field(default_factory=dict)


OPZIONI_STRUTTURATE: dict[str, dict[str, Any]] = {
    "anthropic": {
        "tool_choice": {"type": "auto"},
        "output_config": {"effort": "low"},  # classificare non chiede di ragionare a lungo
    },
    "openai": {"temperature": 0.0},  # la variabilità più bassa: non vuol dire deterministico
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
