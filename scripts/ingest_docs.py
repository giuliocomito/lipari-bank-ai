"""Indicizza i file .md di data/docs inviandoli all'endpoint di ingestione del server avviato.

uv run uvicorn src.main:app        # in un terminale, con Ollama acceso
uv run python -m scripts.ingest_docs

Il livello di visibilità di un documento è la sottocartella in cui si trova
(data/docs/compliance_only/, internal/, risk_only/); i file direttamente in data/docs sono
pubblici. L'ingestione richiede un utente della compliance: lo script accede come Giulia,
con le credenziali del seed di sviluppo, a meno che INGEST_USER e INGEST_PASSWORD dicano
altro.
"""

import asyncio
import os
from pathlib import Path

import httpx

API = "http://localhost:8000"
UTENTE = os.environ.get("INGEST_USER", "grossi")
PASSWORD = os.environ.get("INGEST_PASSWORD", "bootcamp")


async def main() -> None:
    docs_dir = Path("data/docs")
    percorsi = await asyncio.to_thread(lambda: sorted(docs_dir.rglob("*.md")))
    async with httpx.AsyncClient(timeout=60.0) as client:
        login = await client.post(
            f"{API}/api/auth/login", data={"username": UTENTE, "password": PASSWORD}
        )
        login.raise_for_status()  # senza token l'ingestione non può procedere
        token = login.json()["access_token"]
        for path in percorsi:
            # la lettura del file è bloccante, quindi la coroutine la delega a un thread
            content = await asyncio.to_thread(path.read_text, encoding="utf-8")
            visibility = path.parent.name if path.parent != docs_dir else "public"
            response = await client.post(
                f"{API}/api/ai/documents/ingest",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "document_id": path.stem,
                    "content": content,
                    "visibility": visibility,
                    "metadata": {"source": str(path), "title": path.stem.replace("_", " ")},
                },
            )
            print(f"{path.name} [{visibility}]: {response.status_code} {response.json()}")


if __name__ == "__main__":
    asyncio.run(main())
