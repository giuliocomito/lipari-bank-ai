import openai
from openai import AsyncOpenAI

from src.db.models import DIMENSIONI_EMBEDDING
from src.exceptions import LLMProviderError


class EmbeddingClient:
    """Calcola gli embedding tramite un'API compatibile con quella di OpenAI.

    Nel progetto il client punta a Ollama, che serve bge-m3 in locale. Per cambiare fornitore
    bastano indirizzo e modello nella configurazione, più una migration se cambia la dimensione
    del vettore.
    """

    def __init__(self, client: AsyncOpenAI, model: str) -> None:
        self.client = client  # creato dalla factory, uno per processo con il suo pool
        self.model = model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Calcola i vettori di più testi in una sola chiamata, nello stesso ordine."""
        try:
            response = await self.client.embeddings.create(model=self.model, input=texts)
        except openai.APIError as e:  # come nella chat, un errore del fornitore diventa un 502
            raise LLMProviderError("embedding", str(e)) from e
        vettori = [item.embedding for item in response.data]
        if any(len(v) != DIMENSIONI_EMBEDDING for v in vettori):
            # il modello non corrisponde alla colonna: meglio fermarsi qui che scrivere vettori
            # che il database rifiuterebbe, o peggio confrontare vettori di spazi diversi
            raise LLMProviderError(
                "embedding", f"il modello {self.model} non dà vettori da {DIMENSIONI_EMBEDDING}"
            )
        return vettori

    async def embed_one(self, text: str) -> list[float]:
        return (await self.embed([text]))[0]
