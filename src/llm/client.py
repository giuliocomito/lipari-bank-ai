from collections.abc import AsyncGenerator
from typing import Protocol

from src.llm.types import LLMResponse, Message, ToolSpec


class LLMProvider(Protocol):
    @property
    def model(self) -> str:
        """Nome del modello; serve a stimare il costo di uno stream interrotto."""
        ...

    async def complete(
        self, messages: list[Message], max_tokens: int = 500, tools: list[ToolSpec] | None = None
    ) -> LLMResponse:
        """Restituisce la risposta intera con consumo e costo, o le chiamate a strumenti."""
        ...

    def stream(
        self, messages: list[Message], max_tokens: int = 500
    ) -> AsyncGenerator[str | LLMResponse, None]:
        """Produce il testo a pezzi mentre arriva, e per ultima la LLMResponse con il costo.

        Il tipo è AsyncGenerator perché chi lo consuma deve poterlo chiudere con aclose quando il
        client si disconnette; la chiusura si propaga fino alla connessione con il fornitore.
        """
        ...
