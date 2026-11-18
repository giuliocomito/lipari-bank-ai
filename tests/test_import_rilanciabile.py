# Estensione del Giorno 2: lo stesso file importato due volte viene contato una volta sola.
from pathlib import Path

from fastapi.testclient import TestClient
from httpx import Response

from src.main import app
from src.services.import_registry import RegistroImport, get_registro

ESTRATTO = (Path(__file__).resolve().parents[1] / "examples" / "estratto-200.csv").read_bytes()


def test_lo_stesso_file_caricato_due_volte_non_raddoppia_il_conto():
    registro = RegistroImport()  # isolato dagli altri test
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
        seconda = carica(ESTRATTO).json()  # l'ufficio ricarica lo stesso file
        assert prima["imported_count"] == 193 and prima["replayed"] is False
        assert seconda == {**prima, "replayed": True}  # restituisce l'esito del primo import
        assert registro.totale_importate == 193

        # Con Idempotency-Key decide la chiave: stessa chiave e stesso file sono una ripetizione,
        # stessa chiave e file diverso sono un errore del chiamante (409).
        domani = ESTRATTO.replace(b"2026-10-", b"2026-11-")
        assert carica(domani, "ops-2026-11-03").json()["replayed"] is False
        assert carica(domani, "ops-2026-11-03").json()["replayed"] is True
        assert registro.totale_importate == 2 * 193
        conflitto = carica(ESTRATTO, "ops-2026-11-03")
        assert conflitto.status_code == 409
        assert conflitto.json()["error"] == "IDEMPOTENCY_KEY_REUSED"
        assert registro.totale_importate == 2 * 193
    finally:
        app.dependency_overrides.pop(get_registro)  # lascia attivi i finti del conftest
