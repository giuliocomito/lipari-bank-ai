# src/llm/embedding_client.py — i vettori, dallo stesso modello per documenti e domande
import openai
from openai import AsyncOpenAI

from src.db.models import DIMENSIONI_EMBEDDING
from src.exceptions import LLMProviderError


class EmbeddingClient:
    """Il client degli embedding.

    Parla l'API di OpenAI, ma non per forza con OpenAI: nel progetto il client punta a Ollama,
    che sul proprio PC serve il modello bge-m3 con un'API compatibile. Cambiare fornitore di
    embedding è cambiare l'indirizzo e il modello nella configurazione, più una migration se
    cambiano le dimensioni del vettore.
    """

    def __init__(self, client: AsyncOpenAI, model: str) -> None:
        self.client = client  # lo stesso della factory: un pool di connessioni per processo
        self.model = model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """I vettori di più testi in una chiamata, nello stesso ordine dei testi."""
        try:
            response = await self.client.embeddings.create(model=self.model, input=texts)
        except openai.APIError as e:  # come la chat: un guasto del fornitore è un 502, non un bug
            raise LLMProviderError("embedding", str(e)) from e
        vettori = [item.embedding for item in response.data]
        if any(len(v) != DIMENSIONI_EMBEDDING for v in vettori):
            # un modello diverso da quello per cui è fatta la colonna: meglio fermarsi qui che
            # scrivere vettori che il database rifiuta, o peggio confrontare spazi diversi
            raise LLMProviderError(
                "embedding", f"il modello {self.model} non dà vettori da {DIMENSIONI_EMBEDDING}"
            )
        return vettori

    async def embed_one(self, text: str) -> list[float]:
        return (await self.embed([text]))[0]
