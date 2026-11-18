"""Indicizza i file .md di data/docs inviandoli all'endpoint di ingestione del server avviato.

uv run uvicorn src.main:app        # in un terminale, con Ollama acceso
uv run python -m scripts.ingest_docs
"""

import asyncio
from pathlib import Path

import httpx


async def main() -> None:
    docs_dir = Path("data/docs")
    percorsi = await asyncio.to_thread(lambda: sorted(docs_dir.glob("*.md")))
    async with httpx.AsyncClient(timeout=60.0) as client:
        for path in percorsi:
            # la lettura del file è bloccante, quindi la coroutine la delega a un thread
            content = await asyncio.to_thread(path.read_text, encoding="utf-8")
            response = await client.post(
                "http://localhost:8000/api/ai/documents/ingest",
                json={
                    "document_id": path.stem,
                    "content": content,
                    "metadata": {"source": str(path), "title": path.stem.replace("_", " ")},
                },
            )
            print(f"{path.name}: {response.json()}")


if __name__ == "__main__":
    asyncio.run(main())
