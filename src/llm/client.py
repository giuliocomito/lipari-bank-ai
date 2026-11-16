# src/llm/client.py — il contratto di comportamento
from collections.abc import AsyncGenerator
from typing import Protocol

from src.llm.types import LLMResponse, Message, ToolSpec


class LLMProvider(Protocol):
    @property
    def model(self) -> str:
        """Il modello che risponde: serve a stimare il costo di uno stream interrotto."""
        ...

    async def complete(
        self, messages: list[Message], max_tokens: int = 500, tools: list[ToolSpec] | None = None
    ) -> LLMResponse:
        """La risposta intera, con il suo consumo e il suo costo; o le richieste di strumento."""
        ...

    def stream(
        self, messages: list[Message], max_tokens: int = 500
    ) -> AsyncGenerator[str | LLMResponse, None]:
        """I pezzi di testo man mano che arrivano; per ultima la LLMResponse, con il costo.

        È un generatore, non un iteratore qualunque: chi lo usa può chiuderlo (aclose) quando
        il client se ne va, e la chiusura arriva fino alla connessione con il fornitore.
        """
        ...
