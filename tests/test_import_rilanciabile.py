# tests/test_import_rilanciabile.py — l'estensione del Giorno 2: lo stesso file conta una volta
from pathlib import Path

from fastapi.testclient import TestClient
from httpx import Response

from src.main import app
from src.services.import_registry import RegistroImport, get_registro

ESTRATTO = (Path(__file__).resolve().parents[1] / "examples" / "estratto-200.csv").read_bytes()


def test_lo_stesso_file_caricato_due_volte_non_raddoppia_il_conto():
    registro = RegistroImport()  # un registro vuoto, solo per questo test
    app.dependency_overrides[get_registro] = lambda: registro
    try:
        client = TestClient(app)

        def carica(contenuto: bytes, chiave: str | None = None) -> Response:
            headers = {"Idempotency-Key": chiave} if chiave else {}
            return client.post(
                "/api/ai/movements/import",
                files={"file": ("estratto.csv", contenuto, "text/csv")},
                headers=headers,
            )

        prima = carica(ESTRATTO).json()
        seconda = carica(ESTRATTO).json()  # l'ufficio lo ricarica: stesso contenuto
        assert prima["imported_count"] == 193 and prima["replayed"] is False
        assert seconda == {**prima, "replayed": True}  # l'esito di allora, dichiarato
        assert registro.totale_importate == 193  # e il conto non raddoppia

        # Con la chiave dichiarata decide la chiave: la stessa chiave con lo stesso file è una
        # ripetizione, la stessa chiave con un file diverso è un errore del chiamante: 409
        domani = ESTRATTO.replace(b"2026-10-", b"2026-11-")
        assert carica(domani, "ops-2026-11-03").json()["replayed"] is False
        assert carica(domani, "ops-2026-11-03").json()["replayed"] is True
        assert registro.totale_importate == 2 * 193
        conflitto = carica(ESTRATTO, "ops-2026-11-03")
        assert conflitto.status_code == 409
        assert conflitto.json()["error"] == "IDEMPOTENCY_KEY_REUSED"
        assert registro.totale_importate == 2 * 193
    finally:
        app.dependency_overrides.clear()
