from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import DocumentChunk
from src.lib.chunking import chunk_text
from src.llm.embedding_client import EmbeddingClient


def senza_ripetizioni(testo: str) -> str:
    """Toglie i paragrafi ripetuti, come quelli di una pagina incollata due volte.

    Va fatto prima del taglio: con la sovrapposizione, i pezzi di due pagine uguali iniziano in
    punti diversi e non risultano mai identici.
    """
    paragrafi = [p.strip() for p in testo.split("\n\n") if p.strip()]
    return "\n\n".join(dict.fromkeys(paragrafi))


class IngestService:
    """Inserisce un documento nell'indice: lo divide in passaggi, li vettorizza e li salva."""

    LOTTO = 64  # quanti passaggi per chiamata al modello di embedding

    def __init__(self, session: AsyncSession, embedder: EmbeddingClient) -> None:
        self.session = session
        self.embedder = embedder

    async def ingest(
        self, document_id: str, text: str, metadata: dict[str, str] | None = None
    ) -> int:
        """Indicizza il testo e restituisce il numero di passaggi scritti.

        Se il `document_id` esiste già, i suoi passaggi vengono cancellati nella stessa
        transazione e sostituiti.
        """
        await self.session.execute(
            delete(DocumentChunk).where(DocumentChunk.document_id == document_id)
        )

        pezzi = chunk_text(senza_ripetizioni(text))
        if not pezzi:
            await self.session.commit()
            return 0

        for inizio in range(0, len(pezzi), self.LOTTO):
            lotto = pezzi[inizio : inizio + self.LOTTO]
            vettori = await self.embedder.embed(lotto)
            self.session.add_all(
                [
                    DocumentChunk(
                        document_id=document_id,
                        chunk_index=inizio + i,
                        content=testo,
                        embedding=vettore,
                        chunk_metadata=metadata or {},
                    )
                    for i, (testo, vettore) in enumerate(zip(lotto, vettori, strict=True))
                ]
            )

        await self.session.commit()  # il documento entra nell'indice per intero o per niente
        return len(pezzi)
